#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""EVAC reference hardware bridge for a Raspberry Pi (ADR-0032). Not a certified product (brief §2).

Reads dry contacts (fire alarm panel relays), buttons and key switches on GPIO pins, debounces them and reports
every change (``active``/``rest``/``fault``) to EVAC over HTTPS (default) or MQTT, plus a heartbeat every few
seconds. Changes are kept in a small on-disk queue and retried with the same id until EVAC confirms them, so a
network outage or a restart loses nothing and never raises an alarm twice.

Only the Python standard library is required. ``gpiozero`` (on the Pi) reads the pins; ``paho-mqtt`` is needed
only for ``transport = "mqtt"``. ``--simulate`` reads input changes from stdin (``in1 active``) for testing.

Fail-safe (ADR-0034, optional ``[fallback]``): the bridge keeps the event's signed state from every heartbeat and
serves it at ``/evac/<event>/state`` for screens that lost the server. With the event's exported alarm key it
also signs an alarm itself when an input fires and EVAC cannot be reached, following the input's policy
(execute at once; arm after its escalation time; notify never). It never signs an all clear.

    python3 evac_bridge.py --config /etc/evac-bridge.toml
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import logging
import os
import ssl
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("evac-bridge")
VERSION = "1.1.0"
STATES = ("rest", "active", "fault")


# ---------------------------------------------------------------------------------------------- pure helpers
def classify(level: bool, *, active_high: bool) -> str:
    """A digital input (unsupervised): the contact is closed when the pin reads ``active_high``."""
    return "active" if level == active_high else "rest"


def classify_loop(ratio: float, *, rest: tuple[float, float] = (0.35, 0.65),
                  active: tuple[float, float] = (0.05, 0.35)) -> str:
    """A supervised loop measured as a fraction of the supply (ADC, end-of-line resistor).

    With the usual wiring the end-of-line resistor alone gives about half the supply (``rest``), the closed
    contact adds a parallel resistor (``active``), a broken wire reads near the supply and a short near zero:
    both are ``fault``. The bands are configurable per input.
    """
    if active[0] <= ratio < active[1]:
        return "active"
    if rest[0] <= ratio <= rest[1]:
        return "rest"
    return "fault"


class Debouncer:
    """A new state counts only after it has been stable for ``ms`` milliseconds."""

    def __init__(self, ms: int = 200, clock: Callable[[], float] = time.monotonic) -> None:
        self.ms, self.clock = ms, clock
        self.stable: dict[str, str] = {}
        self.pending: dict[str, tuple[str, float]] = {}

    def feed(self, key: str, state: str) -> str | None:
        """Returns the new stable state when it changed, else None."""
        now = self.clock()
        if self.stable.get(key) == state:
            self.pending.pop(key, None)
            return None
        cand = self.pending.get(key)
        if cand is None or cand[0] != state:
            self.pending[key] = (state, now)
            if self.ms > 0:
                return None
        elif (now - cand[1]) * 1000 < self.ms:
            return None
        self.pending.pop(key, None)
        self.stable[key] = state
        return state


def backoff(attempt: int, *, base: float = 1.0, cap: float = 30.0) -> float:
    return min(cap, base * (2 ** max(attempt, 0)))


class Outbox:
    """Input changes waiting for EVAC's confirmation, persisted as JSON (survives restarts)."""

    def __init__(self, path: str | None) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.items: list[dict[str, Any]] = []
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self.items = [i for i in json.load(fh) if isinstance(i, dict) and "id" in i]
            except (OSError, ValueError):
                log.warning("outbox %s unreadable; starting empty", path)

    def _save(self) -> None:
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.items, fh)
        os.replace(tmp, self.path)

    def add(self, key: str, state: str, at: float | None = None) -> dict[str, Any]:
        item = {"id": uuid.uuid4().hex, "input": key, "state": state, "at": time.time() if at is None else at}
        with self.lock:
            self.items.append(item)
            self._save()
        return item

    def peek(self) -> dict[str, Any] | None:
        with self.lock:
            return dict(self.items[0]) if self.items else None

    def mark(self, item_id: str, **values: Any) -> None:
        with self.lock:
            for i in self.items:
                if i["id"] == item_id:
                    i.update(values)
            self._save()

    def done(self, item_id: str) -> None:
        with self.lock:
            self.items = [i for i in self.items if i["id"] != item_id]
            self._save()

    def __len__(self) -> int:
        return len(self.items)


# ---------------------------------------------------------------------------------------------- Ed25519
# RFC 8032 signing in pure Python (a few milliseconds per signature), used when ``cryptography`` is missing.
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


def _recover_x(y: int, sign: int) -> int:
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _add(p: tuple[int, ...], q: tuple[int, ...]) -> tuple[int, int, int, int]:
    a, b = (p[1] - p[0]) * (q[1] - q[0]) % _P, (p[1] + p[0]) * (q[1] + q[0]) % _P
    c, d = 2 * p[3] * q[3] * _D % _P, 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return e * f % _P, g * h % _P, f * g % _P, e * h % _P


def _mul(s: int, p: tuple[int, ...]) -> tuple[int, ...]:
    q: tuple[int, ...] = (0, 1, 1, 0)
    while s:
        if s & 1:
            q = _add(q, p)
        p, s = _add(p, p), s >> 1
    return q


def _compress(p: tuple[int, ...]) -> bytes:
    zi = _inv(p[2])
    x, y = p[0] * zi % _P, p[1] * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def ed25519_sign(seed: bytes, msg: bytes) -> bytes:
    """Ed25519 signature of ``msg`` with the 32-byte private ``seed``."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        return Ed25519PrivateKey.from_private_bytes(seed).sign(msg)
    except ImportError:  # pragma: no cover - the pure version is tested directly
        return _sign_pure(seed, msg)


def _sign_pure(seed: bytes, msg: bytes) -> bytes:
    h = hashlib.sha512(seed).digest()
    a = (int.from_bytes(h[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
    pub = _compress(_mul(a, _G))
    r = int.from_bytes(hashlib.sha512(h[32:] + msg).digest(), "little") % _Q
    big_r = _compress(_mul(r, _G))
    k = int.from_bytes(hashlib.sha512(big_r + pub + msg).digest(), "little") % _Q
    return big_r + ((r + k * a) % _Q).to_bytes(32, "little")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---------------------------------------------------------------------------------------------- fail-safe
SEVERITY = {"normal": 0, "all_clear": 1, "staff_alert": 2, "attention": 3, "shelter_in_place": 4, "evacuate": 5}
ALARMS = ("staff_alert", "attention", "shelter_in_place", "evacuate")


class FallbackState:
    """The event's last signed state (from EVAC, or signed here), persisted, served to screens."""

    def __init__(self, path: str | None = None, *, key: str = "", name: str = "bridge",
                 clock: Callable[[], float] = time.time) -> None:
        self.path, self.name, self.clock = path, name, clock
        self.seed = unb64(key) if key else b""
        self.lock = threading.Lock()
        self.message: dict[str, Any] | None = None
        self.config: dict[str, Any] = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    saved = json.load(fh)
                self.message, self.config = saved.get("message"), saved.get("config") or {}
            except (OSError, ValueError, AttributeError):
                log.warning("state file %s unreadable; starting empty", path)

    @property
    def core(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.message["sig"]["m"]) if self.message else None
        except (KeyError, TypeError, ValueError):
            return None

    def _save(self) -> None:
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"message": self.message, "config": self.config}, fh)
        os.replace(tmp, self.path)

    def update(self, answer: dict[str, Any]) -> None:
        """Take the state and input policies from a heartbeat answer (never go back to an older message)."""
        with self.lock:
            self.config = {k: answer[k] for k in ("event", "inputs") if k in answer} or self.config
            msg = answer.get("state")
            if isinstance(msg, dict) and isinstance(msg.get("sig"), dict):
                try:
                    seq = int(json.loads(msg["sig"]["m"])["seq"])
                except (KeyError, TypeError, ValueError):
                    return
                current = self.core
                if current is None or seq >= int(current.get("seq", 0)):
                    self.message = msg
            self._save()

    def policy(self, key: str) -> dict[str, Any] | None:
        return next((i for i in self.config.get("inputs", []) if i.get("key") == key), None)

    def issue(self, key: str) -> int | None:
        """Sign the alarm of input ``key`` on top of the last state. Returns its ``seq`` (None when impossible)."""
        spec = self.policy(key)
        with self.lock:
            core = self.core
            if not self.seed or spec is None or core is None or spec.get("state") not in ALARMS:
                return None
            new = json.loads(json.dumps(core))
            status = {"st": spec["state"], "d": False}
            zone = spec.get("zone") or ""
            if zone:
                z = new.setdefault("z", {})
                if SEVERITY.get(z.get(zone, {}).get("st", "normal"), 0) < SEVERITY[spec["state"]]:
                    z[zone] = status
            elif SEVERITY.get(new.get("ev", {}).get("st", "normal"), 0) < SEVERITY[spec["state"]]:
                new["ev"] = status
            new.update(seq=int(core["seq"]) + 1, ia=int(self.clock()), **{"is": f"bridge:{self.name}"})
            m = json.dumps(new, sort_keys=True, separators=(",", ":"))
            self.message = {"sig": {"kid": "bridge", "m": m, "s": b64(ed25519_sign(self.seed, m.encode()))}}
            self._save()
            return int(new["seq"])


def due_to_issue(spec: dict[str, Any] | None, waited: float) -> bool:
    """Whether an active input should be signed by the bridge now (EVAC unreachable for ``waited`` seconds)."""
    if not spec:
        return False
    pol = spec.get("policy") or {}
    if pol.get("action") == "execute":
        return True
    if pol.get("action") == "arm" and pol.get("escalate_seconds") is not None:
        return waited >= float(pol["escalate_seconds"])
    return False


def serve_state(state: FallbackState, host: str, port: int, *, cert: str | None = None,
                key: str | None = None) -> http.server.ThreadingHTTPServer:  # pragma: no cover - socket server
    """Serve ``GET /evac/<event>/state`` (the signed state) on the LAN; CORS open, nothing else."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            event = state.config.get("event", "")
            if self.path.split("?")[0].rstrip("/") != f"/evac/{event}/state" or state.message is None:
                self.send_error(404)
                return
            body = json.dumps(state.message).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:
            log.debug("fallback: " + fmt, *args)

    server = http.server.ThreadingHTTPServer((host, port), Handler)
    if cert and key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ---------------------------------------------------------------------------------------------- transports
def _input_body(item: dict[str, Any]) -> dict[str, Any]:
    body = {"input": item["input"], "state": item["state"], "id": item["id"]}
    if item.get("issued_seq"):
        body["issued_seq"] = item["issued_seq"]
    return body


class Rejected(Exception):
    """EVAC refused the request permanently (bad token, unknown input): retrying will not help."""


class HttpsTransport:
    def __init__(self, url: str, token: str, *, ca_file: str | None = None, timeout: float = 5.0) -> None:
        self.url = url.rstrip("/") + "/"
        self.token, self.timeout = token, timeout
        self.ctx = ssl.create_default_context(cafile=ca_file) if url.startswith("https") else None

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json",
                                              "User-Agent": f"evac-bridge/{VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as err:
            if err.code in (400, 401, 404):
                raise Rejected(f"{err.code}: {err.read()[:200]!r}") from err
            raise

    def heartbeat(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.post("heartbeat", body)

    def send(self, item: dict[str, Any]) -> dict[str, Any]:
        return self.post("input", _input_body(item))


class MqttTransport:  # pragma: no cover - needs a broker
    def __init__(self, cfg: dict[str, Any], token: str) -> None:
        import paho.mqtt.client as mqtt

        self.token = token
        self.prefix = str(cfg.get("topic_prefix", "evac")).strip("/")
        self.ident = token[:12]
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"bridge-{self.ident}")
        if cfg.get("username"):
            self.client.username_pw_set(cfg["username"], cfg.get("password"))
        if cfg.get("tls", True):
            self.client.tls_set(ca_certs=cfg.get("ca_file"))
        self.client.connect(cfg["host"], int(cfg.get("port", 8883)), keepalive=30)
        self.client.loop_start()

    def _pub(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        topic = f"{self.prefix}/bridge/{self.ident}/{kind}"
        info = self.client.publish(topic, json.dumps({**body, "token": self.token}), qos=1)
        info.wait_for_publish(timeout=5)
        if not info.is_published():
            raise OSError("not published")
        return {}

    def heartbeat(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._pub("heartbeat", body)

    def send(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._pub("input", _input_body(item))


# ---------------------------------------------------------------------------------------------- the bridge
@dataclass
class InputSpec:
    key: str
    pin: int | None = None
    kind: str = "digital"  # digital | loop (ADC ratio from read_loop) | sim
    active_high: bool = False  # default wiring: pull-up, contact to ground -> closed reads low
    rest_band: tuple[float, float] = (0.35, 0.65)
    active_band: tuple[float, float] = (0.05, 0.35)


@dataclass
class Bridge:
    transport: Any
    inputs: list[InputSpec]
    outbox: Outbox
    heartbeat_seconds: float = 10.0
    debounce_ms: int = 200
    on_status: Callable[[str], None] = lambda s: None
    states: dict[str, str] = field(default_factory=dict)
    fallback: FallbackState | None = None
    clock: Callable[[], float] = time.time

    def __post_init__(self) -> None:
        self.debouncer = Debouncer(self.debounce_ms)
        self.stop = threading.Event()
        self.offline_since: float | None = None

    def observe(self, key: str, state: str) -> None:
        """Feed a raw reading; queue a change once it is stable."""
        new = self.debouncer.feed(key, state)
        if new is not None and new != self.states.get(key):
            self.states[key] = new
            self.outbox.add(key, new, at=self.clock())
            log.info("input %s -> %s (queued, %d waiting)", key, new, len(self.outbox))
            self.tick()

    def _offline(self) -> None:
        if self.offline_since is None:
            self.offline_since = self.clock()
        self.on_status("offline")

    def tick(self) -> list[int]:
        """While EVAC is unreachable: sign queued alarms whose policy says so (fail-safe, ADR-0034)."""
        if self.fallback is None or self.offline_since is None:
            return []
        issued = []
        for item in list(self.outbox.items):
            if item["state"] != "active" or item.get("issued_seq"):
                continue
            waited = self.clock() - max(float(item.get("at", 0)), self.offline_since)
            if due_to_issue(self.fallback.policy(item["input"]), waited):
                seq = self.fallback.issue(item["input"])
                if seq is not None:
                    self.outbox.mark(item["id"], issued_seq=seq)
                    log.warning("EVAC unreachable: alarm of %s signed by the bridge (#%d)", item["input"], seq)
                    issued.append(seq)
        return issued

    def flush(self) -> bool:
        """Send queued changes in order. Returns False when EVAC was unreachable (retry later)."""
        while (item := self.outbox.peek()) is not None:
            try:
                answer = self.transport.send(item)
            except Rejected as err:
                log.error("EVAC refused %s (%s); dropping it", item, err)
                self.outbox.done(item["id"])
                continue
            except (OSError, urllib.error.URLError) as err:
                log.warning("EVAC unreachable (%s); %d change(s) kept", err, len(self.outbox))
                self._offline()
                self.tick()
                return False
            log.info("sent %s %s: %s", item["input"], item["state"], answer.get("result", "ok"))
            self.outbox.done(item["id"])
        return True

    def beat(self) -> bool:
        try:
            answer = self.transport.heartbeat({"inputs": dict(self.states),
                                               "info": {"firmware": f"evac-bridge {VERSION}", "model": "pi"}})
        except Rejected as err:
            log.error("heartbeat refused: %s", err)
            self.on_status("error")
            return False
        except (OSError, urllib.error.URLError) as err:
            log.warning("heartbeat failed: %s", err)
            self._offline()
            self.tick()
            return False
        if isinstance(answer, dict) and answer.get("heartbeat_seconds"):
            self.heartbeat_seconds = max(2.0, float(answer["heartbeat_seconds"]))
        if isinstance(answer, dict) and self.fallback is not None:
            self.fallback.update(answer)
        self.offline_since = None
        self.on_status("online")
        return True

    def run(self) -> None:  # pragma: no cover - long-running loop
        attempt = 0
        while not self.stop.is_set():
            ok = self.flush() and self.beat()
            attempt = 0 if ok else attempt + 1
            # offline with a fail-safe: look at armed inputs every second
            self.stop.wait(self.heartbeat_seconds if ok else min(backoff(attempt), 1.0 if self.fallback else 30.0))
            if not ok:
                self.tick()


def load_config(path: str) -> dict[str, Any]:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def build(cfg: dict[str, Any]) -> Bridge:
    evac = cfg.get("evac", {})
    token = os.environ.get("EVAC_BRIDGE_TOKEN") or evac.get("token", "")
    if evac.get("transport", "https") == "mqtt":  # pragma: no cover - needs a broker
        transport: Any = MqttTransport(cfg.get("mqtt", {}), token)
    else:
        transport = HttpsTransport(evac["url"], token, ca_file=evac.get("ca_file"))
    inputs = [InputSpec(key=i["key"], pin=i.get("pin"), kind=i.get("kind", "digital"),
                        active_high=bool(i.get("active_high", False)),
                        rest_band=tuple(i.get("rest_band", (0.35, 0.65))),  # type: ignore[arg-type]
                        active_band=tuple(i.get("active_band", (0.05, 0.35))))  # type: ignore[arg-type]
              for i in cfg.get("inputs", [])]
    fb_cfg = cfg.get("fallback") or {}
    fallback = None
    if fb_cfg:
        fallback = FallbackState(fb_cfg.get("state_file"),
                                 key=os.environ.get("EVAC_BRIDGE_ALARM_KEY") or fb_cfg.get("alarm_key", ""),
                                 name=str(fb_cfg.get("name") or "bridge"))
    return Bridge(transport, inputs, Outbox(cfg.get("bridge", {}).get("queue_file")),
                  debounce_ms=int(cfg.get("bridge", {}).get("debounce_ms", 200)), fallback=fallback)


def _gpio_loop(bridge: Bridge, poll: float = 0.02) -> None:  # pragma: no cover - needs a Raspberry Pi
    from gpiozero import Button  # type: ignore[import-not-found]

    buttons = {i.key: Button(i.pin, pull_up=not i.active_high) for i in bridge.inputs if i.kind == "digital"}
    while not bridge.stop.is_set():
        for spec in bridge.inputs:
            if spec.key in buttons:
                # gpiozero's is_pressed already accounts for the pull direction: pressed = contact closed
                bridge.observe(spec.key, "active" if buttons[spec.key].is_pressed else "rest")
        time.sleep(poll)


def _stdin_loop(bridge: Bridge) -> None:  # pragma: no cover - manual testing
    for line in sys.stdin:
        parts = line.split()
        if len(parts) == 2 and parts[1] in STATES:
            bridge.debouncer.ms = 0
            bridge.observe(parts[0], parts[1])


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - entry point
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="/etc/evac-bridge.toml")
    ap.add_argument("--simulate", action="store_true", help="read 'key state' lines from stdin instead of GPIO")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    bridge = build(cfg)
    fb = cfg.get("fallback") or {}
    if bridge.fallback is not None and fb.get("listen_port"):
        serve_state(bridge.fallback, str(fb.get("listen_host", "0.0.0.0")), int(fb["listen_port"]),
                    cert=fb.get("cert_file"), key=fb.get("key_file"))
    threading.Thread(target=bridge.run, daemon=True).start()
    try:
        (_stdin_loop if args.simulate else _gpio_loop)(bridge)
    except KeyboardInterrupt:
        pass
    bridge.stop.set()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
