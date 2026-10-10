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
