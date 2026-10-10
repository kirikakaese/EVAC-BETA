#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""EVAC reference hardware bridge for a Raspberry Pi (ADR-0032). Not a certified product (brief §2).

Reads dry contacts (fire alarm panel relays), buttons and key switches on GPIO pins, debounces them and reports
every change (``active``/``rest``/``fault``) to EVAC over HTTPS (default) or MQTT, plus a heartbeat every few
seconds. Changes are kept in a small on-disk queue and retried with the same id until EVAC confirms them, so a
network outage or a restart loses nothing and never raises an alarm twice.

Only the Python standard library is required. ``gpiozero`` (on the Pi) reads the pins; ``paho-mqtt`` is needed
only for ``transport = "mqtt"``. ``--simulate`` reads input changes from stdin (``in1 active``) for testing.

    python3 evac_bridge.py --config /etc/evac-bridge.toml
"""
from __future__ import annotations

import argparse
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
VERSION = "1.0.0"
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

    def add(self, key: str, state: str) -> dict[str, Any]:
        item = {"id": uuid.uuid4().hex, "input": key, "state": state, "at": time.time()}
        with self.lock:
            self.items.append(item)
            self._save()
        return item

    def peek(self) -> dict[str, Any] | None:
        with self.lock:
            return dict(self.items[0]) if self.items else None

    def done(self, item_id: str) -> None:
        with self.lock:
            self.items = [i for i in self.items if i["id"] != item_id]
            self._save()

    def __len__(self) -> int:
        return len(self.items)


# ---------------------------------------------------------------------------------------------- transports
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
        return self.post("input", {"input": item["input"], "state": item["state"], "id": item["id"]})


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
        return self._pub("input", {"input": item["input"], "state": item["state"], "id": item["id"]})


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

    def __post_init__(self) -> None:
        self.debouncer = Debouncer(self.debounce_ms)
        self.stop = threading.Event()

    def observe(self, key: str, state: str) -> None:
        """Feed a raw reading; queue a change once it is stable."""
        new = self.debouncer.feed(key, state)
        if new is not None and new != self.states.get(key):
            self.states[key] = new
            self.outbox.add(key, new)
            log.info("input %s -> %s (queued, %d waiting)", key, new, len(self.outbox))

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
                self.on_status("offline")
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
            self.on_status("offline")
            return False
        if isinstance(answer, dict) and answer.get("heartbeat_seconds"):
            self.heartbeat_seconds = max(2.0, float(answer["heartbeat_seconds"]))
        self.on_status("online")
        return True

    def run(self) -> None:  # pragma: no cover - long-running loop
        attempt = 0
        while not self.stop.is_set():
            ok = self.flush() and self.beat()
            attempt = 0 if ok else attempt + 1
            self.stop.wait(self.heartbeat_seconds if ok else backoff(attempt))


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
    return Bridge(transport, inputs, Outbox(cfg.get("bridge", {}).get("queue_file")),
                  debounce_ms=int(cfg.get("bridge", {}).get("debounce_ms", 200)))


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
    bridge = build(load_config(args.config))
    threading.Thread(target=bridge.run, daemon=True).start()
    try:
        (_stdin_loop if args.simulate else _gpio_loop)(bridge)
    except KeyboardInterrupt:
        pass
    bridge.stop.set()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
