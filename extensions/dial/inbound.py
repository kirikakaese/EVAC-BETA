# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inbound DIAL webhooks (roadmap 4.2, ADR-0037).

DIAL posts ``{type, sent_at, data}`` with ``X-DIAL-Event`` and ``X-DIAL-Signature: sha256=<HMAC>`` (verified by EVAC
before this module runs). DIAL has no delivery id and re-renders ``sent_at`` on every retry, so the idempotency key
is the type plus a hash of ``data``.

- ``emergency.triggered`` (someone dialled an emergency number) -> evacuation trigger ``dial`` through the trigger
  policy (execute / arm / notify). DIAL's own broadcasts (``data.kind == "broadcast"``, also the ones EVAC asked
  for) are not alarms and are ignored.
- ``page.updated`` -> refresh the feeds of the info page data source.
- ``announcement.recorded`` -> import the audio, transcribe (optional) and create an announcement (approval queue,
  or published at once for allow-listed extensions).
- ``dect.*`` -> DECT alert (status data source, operations log, staff notification for problems).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from apps.core import outbox
from apps.core.plugins import WebhookResult

from . import link
from .models import DectAlert, Recording

log = logging.getLogger("evac.dial")

SOURCE = "dial"
RECORDING_JOB = "dial.recording"
REFRESH_JOB = "dial.refresh"


def delivery_id(headers: Any, body: bytes, payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    data = json.dumps(payload.get("data"), sort_keys=True, separators=(",", ":"), default=str)
    kind = str(payload.get("type") or headers.get("X-DIAL-Event") or "")
    return f"dial:{kind}:{hashlib.sha256(data.encode()).hexdigest()[:40]}"


def handle(config: Any, headers: Any, body: bytes, payload: Any) -> WebhookResult:
    from apps.extensions import services as ext

    if config.event_id is None:
        return WebhookResult(400, {"ok": False, "error": "configure DIAL per event"})
    if not isinstance(payload, dict):
        return WebhookResult(400, {"ok": False, "error": "expected a JSON object"})
    kind = str(headers.get("X-DIAL-Event") or payload.get("type") or "")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    want = (link.settings_of(config).get("event") or "").strip()
    if data.get("event") and want and data["event"] != want:
        ext.write_log(config, "warn", f"DIAL webhook for another DIAL event ({data['event']}) ignored")
        return WebhookResult(200, {"ok": True, "ignored": "other event"})
    if kind == "emergency.triggered":
        return emergency(config, data)
    if kind == "page.updated":
        return page_updated(config, data)
    if kind == "announcement.recorded":
        return recorded(config, data)
    if kind.startswith("dect."):
        return dect(config, kind, data)
    return WebhookResult(200, {"ok": True, "ignored": kind or "no type"})


# ------------------------------------------------------------------ emergency
def _stage(config: Any, event: Any) -> str | None:
    """The configured stage, or the closest alarm stage the event has (the simple model only knows evacuate)."""
    from apps.evacuation import machine, services

    wanted = link.settings_of(config).get("emergency_stage") or "staff_alert"
    enabled = {s.value for s in services.config(event).enabled if s in machine.ALARMS}
    if wanted in enabled:
        return str(wanted)
    order = sorted(enabled, key=lambda s: machine.SEVERITY[machine.State(s)])
    above = [s for s in order if machine.SEVERITY[machine.State(s)] >= machine.SEVERITY[machine.State(wanted)]]
    return (above or order or [None])[0]


def emergency(config: Any, data: dict[str, Any]) -> WebhookResult:
    from apps.core import modules
    from apps.extensions import services as ext

    if data.get("kind") == "broadcast":
        return WebhookResult(200, {"ok": True, "ignored": "broadcast"})
    if not config.feature_enabled("trigger"):
        return WebhookResult(200, {"ok": True, "ignored": "trigger switched off"})
    event = config.event
    number = str(data.get("number") or "")
    allowed = link.csv(link.settings_of(config).get("emergency_numbers"))
    if allowed and number not in allowed:
        ext.write_log(config, "info", f"Emergency number {number} dialled in DIAL (not set to trigger)")
        return WebhookResult(200, {"ok": True, "ignored": "number"})
    if not modules.is_enabled("evacuation", event):
        ext.write_log(config, "warn", f"Emergency call to {number} in DIAL: the evacuation module is off")
        return WebhookResult(409, {"ok": False, "error": "evacuation module is off"})
    if modules.acknowledgement_needed("evacuation", event):
        ext.write_log(config, "warn", f"Emergency call to {number} in DIAL: the evacuation safety statement is not "
                                      "accepted yet")
        return WebhookResult(409, {"ok": False, "error": "evacuation safety statement not accepted"})
    from apps.evacuation import machine, triggers

    stage = _stage(config, event)
    if stage is None:
        return WebhookResult(409, {"ok": False, "error": "no alarm stage enabled"})
    caller = str(data.get("caller") or "")
    reason = _("Emergency call to %(n)s in DIAL") % {"n": number} + (
        _(" from extension %(c)s") % {"c": caller} if caller else "")
    try:
        outcome = triggers.trigger(event, stage, source=SOURCE, reason=reason, check_perms=False,
                                   key=f"dial:{config.pk}:incident:{data.get('incident_id') or data.get('at')}")
    except machine.Refused as exc:
        ext.write_log(config, "warn", f"Emergency call to {number}: {exc}")
        return WebhookResult(409, {"ok": False, "error": str(exc)})
    ext.write_log(config, "warn", f"Emergency call to {number} in DIAL -> {stage}: {outcome.result}",
                  caller=caller, incident=data.get("incident_id"))
    return WebhookResult(200, {"ok": True, "result": outcome.result,
                               "request": str(outcome.request.pk) if outcome.request else None})


# ------------------------------------------------------------------ info pages
def page_updated(config: Any, data: dict[str, Any]) -> WebhookResult:
    outbox.enqueue(REFRESH_JOB, {"config": str(config.pk), "sources": ["dial.pages"]}, event=config.event,
                   key=f"dial-refresh:{config.pk}:pages:{data.get('id')}:{data.get('updated_at')}")
    return WebhookResult(200, {"ok": True, "refresh": "pages"})


# ------------------------------------------------------------------ DECT
PROBLEMS = {"dect.rfp.down", "dect.sync.degraded", "dect.omm.unreachable"}


def dect(config: Any, kind: str, data: dict[str, Any]) -> WebhookResult:
    from apps.extensions import services as ext

    at = parse_datetime(str(data.get("at") or "")) or timezone.now()
    alert = DectAlert.objects.create(config=config, event=config.event, kind=kind[len("dect."):][:40],
                                     severity=str(data.get("severity") or "")[:10],
                                     message=str(data.get("message") or "")[:500], rfp=str(data.get("rfp") or "")[:120],
                                     dial_id=str(data.get("id") or "")[:40], at=at)
    ext.write_log(config, "warn" if kind in PROBLEMS else "info", f"DECT {alert.kind}: {alert.message or alert.rfp}")
    from . import ops

    ops.dect_alert(config, alert, problem=kind in PROBLEMS)
    outbox.enqueue(REFRESH_JOB, {"config": str(config.pk), "sources": ["dial.dect"], "snapshots": ["dect"]},
                   event=config.event,
                   key=f"dial-refresh:{config.pk}:dect:{alert.pk}")
    return WebhookResult(200, {"ok": True, "alert": str(alert.pk)})


# ------------------------------------------------------------------ recordings
def recorded(config: Any, data: dict[str, Any]) -> WebhookResult:
    if not config.feature_enabled("recordings"):
        return WebhookResult(200, {"ok": True, "ignored": "recordings switched off"})
    rec = Recording.objects.create(config=config, event=config.event, extension=str(data.get("extension") or "")[:40],
                                   audio=str(data.get("audio") or "")[:300],
                                   duration=max(0, int(data.get("duration") or 0)))
    outbox.enqueue(RECORDING_JOB, {"recording": str(rec.pk)}, event=config.event, key=f"dial-recording:{rec.pk}")
    return WebhookResult(200, {"ok": True, "recording": str(rec.pk)})
