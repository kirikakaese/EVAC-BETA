# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hardware trigger bridges (brief §8.3, ADR-0032): authentication, input changes, line supervision.

A bridge reports every input change (``active``, ``rest``, ``fault``) and a heartbeat every 10 seconds, over
HTTPS (``/bridge/v1/...``) or MQTT (``extensions/mqtt``); both end here.

- ``active``: the input's stage is triggered through the ``bridge`` source (default policy *arm*, ADR-0003);
  the bridge's idempotency key makes retries after a lost answer harmless.
- ``rest`` (e.g. the fire panel was reset): the alarm stays; the control room is told "contact restored".
  Only people end alarms.
- ``fault`` (broken loop, end-of-line resistor out of range) and a missing heartbeat (30 s): a loud alert to the
  control room and the bridge page, never a public alarm.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import audit

from . import machine, policy, triggers
from .machine import Refused, State
from .models import Bridge

PREFIX = "evacb_"
HEARTBEAT_SECONDS = 10
OFFLINE_AFTER = 30
INPUT_STATES = ("rest", "active", "fault")


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create(event: Any, name: str, *, actor: Any = None, request: Any = None) -> tuple[Bridge, str]:
    raw = PREFIX + secrets.token_urlsafe(32)
    bridge = Bridge.objects.create(event=event, name=name[:100], token_hash=hash_token(raw), token_prefix=raw[:12],
                                   created_by=actor if getattr(actor, "pk", None) else None)
    audit.log(action="evacuation.bridge_created", actor=actor, event=event, target=bridge, request=request,
              message=bridge.name)
    return bridge, raw


def rotate(bridge: Bridge, *, actor: Any = None, request: Any = None) -> str:
    raw = PREFIX + secrets.token_urlsafe(32)
    bridge.token_hash, bridge.token_prefix = hash_token(raw), raw[:12]
    bridge.save(update_fields=["token_hash", "token_prefix"])
    audit.log(action="evacuation.bridge_token_rotated", actor=actor, event=bridge.event, target=bridge,
              request=request, message=bridge.name)
    return raw


def delete(bridge: Bridge, *, actor: Any = None, request: Any = None) -> None:
    audit.log(action="evacuation.bridge_deleted", actor=actor, event=bridge.event, target=bridge, request=request,
              message=bridge.name)
    bridge.delete()


def authenticate(raw: str) -> Bridge | None:
    if not raw or not raw.startswith(PREFIX):
        return None
    bridge: Bridge | None = Bridge.objects.select_related("event").filter(token_hash=hash_token(raw)).first()
    return bridge


def parse_inputs(text: str, zones: dict[str, str]) -> list[dict[str, str]]:
    """``key; label; stage; zone name (optional)`` per line → inputs. Raises ValueError with a readable reason."""
    out: list[dict[str, str]] = []
    alarms = {s.value for s in machine.ALARMS}
    by_name = {v.lower(): k for k, v in zones.items()}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 3:
            raise ValueError(_("Line %(n)s: write “key; label; stage; zone”.") % {"n": n})
        key, label, stage = parts[:3]
        zone_name = parts[3] if len(parts) > 3 else ""
        if not key or len(key) > 40 or any(o["key"] == key for o in out):
            raise ValueError(_("Line %(n)s: the key must be unique and short.") % {"n": n})
        if stage not in alarms:
            choices = ", ".join(sorted(alarms))
            raise ValueError(_("Line %(n)s: the stage must be one of %(s)s.") % {"n": n, "s": choices})
        zone = ""
        if zone_name:
            zone = by_name.get(zone_name.lower(), "")
            if not zone:
                raise ValueError(_("Line %(n)s: unknown zone “%(z)s”.") % {"n": n, "z": zone_name})
        out.append({"key": key, "label": label[:100] or key, "state": stage, "zone": zone})
    return out


def format_inputs(bridge: Bridge, zones: dict[str, str]) -> str:
    lines = []
    for i in bridge.inputs:
        parts = [i["key"], i.get("label", ""), i["state"]]
        if i.get("zone") in zones:
            parts.append(zones[i["zone"]])
        lines.append("; ".join(parts))
    return "\n".join(lines)


def set_inputs(bridge: Bridge, inputs: list[dict[str, str]], *, actor: Any = None, request: Any = None) -> None:
    before = bridge.inputs
    bridge.inputs = inputs
    bridge.save(update_fields=["inputs"])
    audit.log(action="evacuation.bridge_configured", actor=actor, event=bridge.event, target=bridge, request=request,
              message=bridge.name, changes={"inputs": [before, inputs]})


def config_for(bridge: Bridge) -> dict[str, Any]:
    """What the bridge needs to know (answer to every heartbeat)."""
    return {"name": bridge.name, "event": bridge.event.slug, "heartbeat_seconds": HEARTBEAT_SECONDS,
            "inputs": [{"key": i["key"], "label": i.get("label", ""), "state": i["state"]} for i in bridge.inputs]}


def _alert(bridge: Bridge, title: str, body: str = "", level: str = "err") -> None:
    from django.urls import reverse

    from apps.core.notify import notify

    notify(triggers.control_room(bridge.event), title, body=body, level=level, event=bridge.event,
           url=reverse("evacuation:policies", args=[bridge.event.slug]))


def heartbeat(bridge: Bridge, *, inputs: dict[str, str] | None = None, info: dict[str, Any] | None = None,
              ip: str | None = None, transport: str = "https") -> dict[str, Any]:
    """Record a heartbeat; input states in it are handled like changes (a missed change is caught up)."""
    with transaction.atomic():
        bridge = Bridge.objects.select_for_update().select_related("event").get(pk=bridge.pk)
        back = not bridge.online and bridge.last_seen is not None
        status = dict(bridge.status or {})
        status["info"] = {k: str(v)[:100] for k, v in (info or {}).items()
                          if k in ("firmware", "uptime", "ip", "rssi", "model")}
        bridge.online, bridge.last_seen, bridge.last_ip, bridge.transport = True, timezone.now(), ip, transport
        bridge.status = status
        bridge.save(update_fields=["online", "last_seen", "last_ip", "transport", "status"])
        if back:
            audit.log(action="evacuation.bridge_online", event=bridge.event, target=bridge, message=bridge.name)
            _alert(bridge, _("Bridge back online: %(b)s") % {"b": bridge.name}, level="info")
    stamp = f"{bridge.last_seen:%Y%m%d%H%M%S}"
    for key, state in (inputs or {}).items():
        current = (status.get("inputs") or {}).get(key)
        if state in INPUT_STATES and state != current:
            report(bridge, key, state, event_key=f"hb:{key}:{state}:{stamp}")
    return config_for(bridge)


@dataclass
class Result:
    result: str
    request: str | None = None
    detail: str = ""


def report(bridge: Bridge, key: str, state: str, *, event_key: str = "", at: str = "") -> Result:
    """An input changed. ``event_key`` is the bridge's idempotency id of this change."""
    bridge.refresh_from_db()
    spec = bridge.input(key)
    if spec is None:
        return Result("unknown_input", detail=key)
    if state not in INPUT_STATES:
        return Result("bad_state", detail=state)
    status = dict(bridge.status or {})
    inputs = dict(status.get("inputs") or {})
    before = inputs.get(key)
    inputs[key] = state
    status["inputs"] = inputs
    Bridge.objects.filter(pk=bridge.pk).update(status=status)
    label = spec.get("label") or key
    if state == "fault":
        if before != "fault":
            audit.log(action="evacuation.bridge_input_fault", event=bridge.event, target=bridge,
                      message=f"{bridge.name}: {label}")
            _alert(bridge, _("Input fault: %(b)s · %(i)s") % {"b": bridge.name, "i": label},
                   _("Check the wiring (broken loop or short circuit). No alarm was raised."))
        return Result("fault_reported")
    if state == "rest":
        if before == "active":
            audit.log(action="evacuation.bridge_contact_restored", event=bridge.event, target=bridge,
                      message=f"{bridge.name}: {label}")
            _alert(bridge, _("Contact restored: %(b)s · %(i)s") % {"b": bridge.name, "i": label},
                   _("The alarm stays until a person gives the all clear."), level="warn")
        elif before == "fault":
            audit.log(action="evacuation.bridge_input_ok", event=bridge.event, target=bridge,
                      message=f"{bridge.name}: {label}")
        return Result("noted")
    zone = None
    if spec.get("zone"):
        from apps.venues.models import Zone

        zone = Zone.objects.filter(pk=spec["zone"]).first()
    idem = f"bridge:{bridge.pk}:{event_key}"[:100] if event_key else ""
    try:
        out = triggers.trigger(bridge.event, State(spec["state"]), source=policy.BRIDGE, zone=zone,
                               reason=f"{bridge.name}: {label}", key=idem, check_perms=False)
    except Refused as err:
        # e.g. the state is already active: nothing to do, but the control room should know the input fired
        audit.log(action="evacuation.bridge_trigger_refused", event=bridge.event, target=bridge,
                  message=f"{bridge.name}: {label}: {err.message}")
        return Result("refused", detail=err.code)
    return Result(out.result, str(out.request.pk) if out.request else None)


def sweep(now: Any = None) -> int:
    """Mark bridges without a heartbeat for ``OFFLINE_AFTER`` seconds offline and alert (Celery beat)."""
    now = now or timezone.now()
    n = 0
    for bridge in Bridge.objects.filter(online=True, last_seen__lt=now - timedelta(seconds=OFFLINE_AFTER)) \
            .select_related("event"):
        Bridge.objects.filter(pk=bridge.pk).update(online=False)
        audit.log(action="evacuation.bridge_offline", event=bridge.event, target=bridge, message=bridge.name)
        _alert(bridge, _("Bridge offline: %(b)s") % {"b": bridge.name},
               _("No heartbeat for %(s)s seconds. Its inputs cannot raise alarms until it is back.")
               % {"s": OFFLINE_AFTER})
        n += 1
    return n
