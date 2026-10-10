# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reference bridge: input classification, debouncing, the persistent outbox and sending (no hardware)."""
import importlib.util
import json
import pathlib
import sys
import urllib.error

import pytest

spec = importlib.util.spec_from_file_location("evac_bridge", pathlib.Path(__file__).parents[1] / "evac_bridge.py")
eb = importlib.util.module_from_spec(spec)
sys.modules["evac_bridge"] = eb  # dataclasses resolve their module while the file executes
spec.loader.exec_module(eb)


def test_classify():
    assert eb.classify(False, active_high=False) == "active" and eb.classify(True, active_high=False) == "rest"
    assert eb.classify(True, active_high=True) == "active"
    assert eb.classify_loop(0.5) == "rest" and eb.classify_loop(0.2) == "active"
    assert eb.classify_loop(0.98) == "fault" and eb.classify_loop(0.01) == "fault"


def test_debouncer():
    t = [0.0]
    d = eb.Debouncer(200, clock=lambda: t[0])
    assert d.feed("a", "rest") is None
    t[0] = 0.25
    assert d.feed("a", "rest") == "rest"
    assert d.feed("a", "active") is None  # a glitch
    t[0] = 0.3
    assert d.feed("a", "rest") is None and d.stable["a"] == "rest"
    assert d.feed("a", "active") is None
    t[0] = 0.6
    assert d.feed("a", "active") == "active"
    assert eb.Debouncer(0).feed("b", "active") == "active"


def test_backoff():
    assert [eb.backoff(n) for n in range(7)] == [1, 2, 4, 8, 16, 30, 30]


def test_outbox_persists(tmp_path):
    path = str(tmp_path / "q.json")
    box = eb.Outbox(path)
    a, b = box.add("in1", "active"), box.add("in1", "rest")
    again = eb.Outbox(path)
    assert [i["id"] for i in again.items] == [a["id"], b["id"]] and again.peek()["state"] == "active"
    again.done(a["id"])
    assert len(eb.Outbox(path)) == 1
    (tmp_path / "bad.json").write_text("{nope")
    assert len(eb.Outbox(str(tmp_path / "bad.json"))) == 0
    assert eb.Outbox(None).add("x", "rest")["input"] == "x"


class FakeTransport:
    def __init__(self, fail=0, reject=()):
        self.fail, self.reject, self.sent, self.beats = fail, set(reject), [], []

    def send(self, item):
        if self.fail:
            self.fail -= 1
            raise urllib.error.URLError("down")
        if item["input"] in self.reject:
            raise eb.Rejected("404")
        self.sent.append(item)
        return {"result": "armed"}

    def heartbeat(self, body):
        if self.fail:
            raise OSError("down")
        self.beats.append(body)
        return {"heartbeat_seconds": 5}


def test_bridge_queues_until_confirmed(tmp_path):
    statuses = []
    tr = FakeTransport(fail=1, reject={"ghost"})
    br = eb.Bridge(tr, [eb.InputSpec("in1", 17)], eb.Outbox(str(tmp_path / "q.json")), debounce_ms=0,
                   on_status=statuses.append)
    br.observe("in1", "active")
    br.observe("in1", "active")  # no change: nothing new
    assert len(br.outbox) == 1
    assert br.flush() is False and statuses[-1] == "offline" and len(br.outbox) == 1  # kept for the retry
    br.observe("ghost", "active")
    assert br.flush() is True and [i["input"] for i in tr.sent] == ["in1"] and len(br.outbox) == 0
    assert br.beat() is True and tr.beats[-1]["inputs"] == {"in1": "active", "ghost": "active"}
    assert br.heartbeat_seconds == 5 and statuses[-1] == "online"


def test_beat_failures():
    class Refuse(FakeTransport):
        def heartbeat(self, body):
            raise eb.Rejected("401")

    br = eb.Bridge(Refuse(), [], eb.Outbox(None))
    assert br.beat() is False
    br = eb.Bridge(FakeTransport(fail=1), [], eb.Outbox(None))
    assert br.beat() is False


def test_build_and_https(tmp_path, monkeypatch):
    cfg = tmp_path / "b.toml"
    cfg.write_text('[evac]\nurl = "http://127.0.0.1:9/bridge/v1"\ntoken = "evacb_x"\n'
                   '[[inputs]]\nkey = "in1"\npin = 17\n')
    br = eb.build(eb.load_config(str(cfg)))
    assert br.inputs[0].key == "in1" and br.transport.url.endswith("/bridge/v1/")
    calls = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.body

    def fake(req, timeout, context):
        calls.append((req.full_url, json.loads(req.data), req.headers["Authorization"]))
        return Resp(b'{"result": "armed"}')

    monkeypatch.setattr(eb.urllib.request, "urlopen", fake)
    assert br.transport.send({"input": "in1", "state": "active", "id": "1"}) == {"result": "armed"}
    assert calls[0][0].endswith("/input") and calls[0][2] == "Bearer evacb_x"

    def refuse(req, timeout, context):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)

    monkeypatch.setattr(eb.urllib.request, "urlopen", refuse)
    with pytest.raises(eb.Rejected):
        br.transport.heartbeat({})


# ------------------------------------------------------------------------------------------- fail-safe
def _keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())
    return key, eb.b64(seed)


def _signed(key, core):
    m = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return {"sig": {"kid": "k", "m": m, "s": eb.b64(key.sign(m.encode()))}}


def _answer(key, seq=7, ev="normal", policy=None):
    core = {"e": "demo", "sc": "*", "seq": seq, "ia": 1, "ev": {"st": ev, "d": False}, "z": {}, "b": []}
    return {"event": "demo", "heartbeat_seconds": 10, "state": _signed(key, core),
            "inputs": [{"key": "in1", "state": "evacuate", "zone": "", "policy": policy or {"action": "execute"}},
                       {"key": "z1", "state": "attention", "zone": "zone-a",
                        "policy": {"action": "arm", "escalate_seconds": 120}},
                       {"key": "n", "state": "evacuate", "policy": {"action": "notify"}}]}


def test_pure_ed25519_matches_cryptography():
    key, seed = _keypair()
    for msg in (b"", b"abc", b"x" * 300):
        assert eb._sign_pure(eb.unb64(seed), msg) == key.sign(msg)
        assert eb.ed25519_sign(eb.unb64(seed), msg) == key.sign(msg)


def test_due_to_issue():
    assert eb.due_to_issue({"policy": {"action": "execute"}}, 0)
    assert not eb.due_to_issue({"policy": {"action": "arm", "escalate_seconds": 120}}, 119)
    assert eb.due_to_issue({"policy": {"action": "arm", "escalate_seconds": 120}}, 120)
    assert not eb.due_to_issue({"policy": {"action": "arm", "escalate_seconds": None}}, 9999)
    assert not eb.due_to_issue({"policy": {"action": "notify"}}, 9999)
    assert not eb.due_to_issue(None, 0)


def test_fallback_state_issue_and_persist(tmp_path):
    key, seed = _keypair()
    path = str(tmp_path / "s.json")
    fb = eb.FallbackState(path, key=seed, name="hall-a", clock=lambda: 1000)
    assert fb.issue("in1") is None  # no state yet
    fb.update(_answer(key, seq=7))
    assert fb.core["seq"] == 7 and fb.policy("in1")["state"] == "evacuate"
    assert fb.issue("nope") is None
    assert fb.issue("in1") == 8
    core = json.loads(fb.message["sig"]["m"])
    assert core["ev"] == {"st": "evacuate", "d": False} and core["is"] == "bridge:hall-a" and core["ia"] == 1000
    key.public_key().verify(eb.unb64(fb.message["sig"]["s"]), fb.message["sig"]["m"].encode())
    assert fb.issue("z1") == 9 and json.loads(fb.message["sig"]["m"])["z"]["zone-a"]["st"] == "attention"
    # an older message from EVAC does not replace it; a newer one does; it survives a restart
    fb.update(_answer(key, seq=8))
    assert fb.core["seq"] == 9
    again = eb.FallbackState(path, key=seed)
    assert again.core["seq"] == 9 and again.policy("z1")["zone"] == "zone-a"
    again.update(_answer(key, seq=12, ev="all_clear"))
    assert again.core["seq"] == 12
    # never lowers a more severe state
    fb2 = eb.FallbackState(None, key=seed)
    fb2.update(_answer(key, seq=3, ev="evacuate"))
    fb2.config["inputs"][0]["state"] = "attention"
    fb2.issue("in1")
    assert json.loads(fb2.message["sig"]["m"])["ev"]["st"] == "evacuate"
    # without a key it relays only
    assert eb.FallbackState(None).issue("in1") is None
    (tmp_path / "bad.json").write_text("{")
    assert eb.FallbackState(str(tmp_path / "bad.json")).message is None
    fb2.update({"state": {"sig": {"m": "nope"}}})
    assert fb2.core["seq"] == 4


def test_bridge_signs_when_offline(tmp_path):
    key, seed = _keypair()
    t = [1000.0]
    tr = FakeTransport()
    fb = eb.FallbackState(None, key=seed, clock=lambda: t[0])
    br = eb.Bridge(tr, [eb.InputSpec("in1"), eb.InputSpec("z1")], eb.Outbox(None), debounce_ms=0, fallback=fb,
                   clock=lambda: t[0])
    tr.beats_answer = _answer(key, seq=7)
    tr.heartbeat = lambda body: tr.beats_answer
    assert br.beat() and fb.core["seq"] == 7
    assert br.tick() == []  # online: EVAC decides
    tr.fail = 2
    br.observe("z1", "active")  # armed with 120 s: not yet
    br.observe("in1", "active")
    assert br.flush() is False and br.offline_since == 1000.0
    issued = [i.get("issued_seq") for i in br.outbox.items]
    assert issued == [None, 8]  # execute policy: signed at once
    t[0] += 121
    assert br.tick() == [9] and br.tick() == []
    assert br.flush() is False  # still down
    tr.fail = 0
    assert br.flush() is True
    assert [i.get("issued_seq") for i in tr.sent] == [9, 8]
    assert eb._input_body(tr.sent[0])["issued_seq"] == 9 and "issued_seq" not in eb._input_body(
        {"input": "a", "state": "rest", "id": "x"})
    assert br.beat() and br.offline_since is None
