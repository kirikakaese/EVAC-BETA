# SPDX-License-Identifier: AGPL-3.0-or-later
"""The MQTT side of hardware bridges. :func:`handle` is transport-independent and tested without a broker.

Topics (``<prefix>`` = topic prefix setting, ``<id>`` = the bridge token's first 12 characters, any value works):
``<prefix>/bridge/<id>/heartbeat`` and ``<prefix>/bridge/<id>/input`` with the same JSON bodies as the HTTPS API
plus ``"token": "evacb_..."``. Heartbeats are answered on ``<prefix>/bridge/<id>/config``.
"""
from __future__ import annotations

import json
import logging
import ssl
import time
from typing import Any

from apps.core.plugins import ConnectionResult

log = logging.getLogger("evac.mqtt")


def config() -> Any:
    from apps.extensions.models import ExtensionConfig

    return ExtensionConfig.objects.filter(extension="mqtt", event__isnull=True, enabled=True).first()


def prefix_of(cfg: Any) -> str:
    return str((cfg.settings or {}).get("topic_prefix") or "evac").strip("/")


def handle(topic: str, payload: bytes, prefix: str = "evac") -> tuple[str, dict[str, Any]] | None:
    """Process one message; returns ``(reply topic, reply body)`` or None."""
    from apps.core import modules
    from apps.evacuation import bridges

    parts = topic.split("/")
    base = prefix.split("/")
    if parts[:len(base)] != base or len(parts) != len(base) + 3 or parts[len(base)] != "bridge":
        return None
    ident, kind = parts[-2], parts[-1]
    try:
        body = json.loads(payload or b"{}")
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    bridge = bridges.authenticate(str(body.get("token", "")))
    if bridge is None or not modules.is_enabled("evacuation", bridge.event):
        log.warning("mqtt: rejected message on %s", topic)
        return None
    reply = f"{prefix}/bridge/{ident}/config"
    if kind == "heartbeat":
        inputs = body.get("inputs") if isinstance(body.get("inputs"), dict) else {}
        info = body.get("info") if isinstance(body.get("info"), dict) else {}
        cfg = bridges.heartbeat(bridge, inputs={str(k): str(v) for k, v in inputs.items()}, info=info,
                                transport="mqtt")
        return reply, cfg
    if kind == "input":
        issued = body.get("issued_seq")
        res = bridges.report(bridge, str(body.get("input", "")), str(body.get("state", "")),
                             event_key=str(body.get("id", ""))[:60],
                             issued_seq=issued if isinstance(issued, int) and not isinstance(issued, bool) else None)
        return f"{prefix}/bridge/{ident}/result", {"id": body.get("id"), "result": res.result}
    return None


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT wildcards: ``+`` one level, ``#`` the rest."""
    pp, tt = pattern.split("/"), topic.split("/")
    for i, p in enumerate(pp):
        if p == "#":
            return True
        if i >= len(tt) or (p != "+" and p != tt[i]):
            return False
    return len(pp) == len(tt)


def dispatch(topic: str, payload: bytes, prefix: str = "evac") -> bool:
    """Messages for modules (``r.mqtt_topic``, e.g. occupancy sensors). Returns whether a module took it."""
    from apps.core.registry import registry

    base = prefix + "/"
    if not topic.startswith(base):
        return False
    rest = topic[len(base):]
    for spec in registry.ensure_loaded().mqtt_topics.values():
        if topic_matches(spec.pattern, rest):
            spec.handler(rest, payload)
            return True
    return False


def subscriptions(prefix: str) -> list[tuple[str, int]]:
    from apps.core.registry import registry

    return [(f"{prefix}/bridge/+/heartbeat", 1), (f"{prefix}/bridge/+/input", 1)] + [
        (f"{prefix}/{spec.pattern}", 1) for spec in registry.ensure_loaded().mqtt_topics.values()]


def _client(cfg: Any) -> Any:
    import paho.mqtt.client as mqtt

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"evac-{int(time.time())}")
    s = cfg.settings or {}
    if s.get("username"):
        c.username_pw_set(s["username"], cfg.secret("password") or None)
    if s.get("tls", True):
        c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    return c


def test_connection(cfg: Any) -> ConnectionResult:
    s = cfg.settings or {}
    try:
        c = _client(cfg)
        rc = c.connect(s.get("host", ""), int(s.get("port") or 8883), keepalive=10)
        c.disconnect()
    except Exception as err:  # noqa: BLE001 - every failure is reported to the admin
        return ConnectionResult(False, f"{type(err).__name__}: {err}")
    return ConnectionResult(rc == 0, "Connected to the broker." if rc == 0 else f"Broker answered {rc}.")


def _session(cfg: Any, stop_after: float | None) -> None:  # pragma: no cover - needs a broker
    """One connection with the current settings; returns when they change (or after ``stop_after`` s)."""
    import django.db

    prefix = prefix_of(cfg)
    s = cfg.settings or {}
    c = _client(cfg)

    def on_connect(client: Any, userdata: Any, flags: Any, rc: Any, props: Any = None) -> None:
        topics = subscriptions(prefix)
        client.subscribe(topics)
        log.info("mqtt: connected, subscribed to %s", ", ".join(t for t, _q in topics))

    def on_message(client: Any, userdata: Any, msg: Any) -> None:
        try:
            if dispatch(msg.topic, msg.payload, prefix):
                return
            out = handle(msg.topic, msg.payload, prefix)
        except Exception:  # noqa: BLE001 - one bad message must not stop the loop
            log.exception("mqtt: failed on %s", msg.topic)
            return
        finally:
            django.db.close_old_connections()
        if out is not None:
            client.publish(out[0], json.dumps(out[1]), qos=1)

    c.on_connect, c.on_message = on_connect, on_message
    c.reconnect_delay_set(min_delay=1, max_delay=30)
    try:
        c.connect(s.get("host", ""), int(s.get("port") or 8883), keepalive=30)
    except Exception as err:  # noqa: BLE001
        log.warning("mqtt: cannot connect (%s); retrying in 10 s", err)
        time.sleep(10)
        return
    started = time.monotonic()
    c.loop_start()
    try:
        while stop_after is None or time.monotonic() - started < stop_after:
            time.sleep(15)
            fresh = config()
            if fresh is None or fresh.updated_at != cfg.updated_at:
                log.info("mqtt: settings changed; reconnecting")
                break
    finally:
        c.loop_stop()
        c.disconnect()


def run(stop_after: float | None = None) -> None:  # pragma: no cover - needs a broker; handle() is tested
    """Subscribe and dispatch until stopped; reconnects with backoff and after settings changes."""
    while True:
        cfg = config()
        if cfg is None:
            log.info("mqtt: extension not configured; checking again in 30 s")
            time.sleep(30)
            continue
        _session(cfg, stop_after)
        if stop_after is not None:
            return
