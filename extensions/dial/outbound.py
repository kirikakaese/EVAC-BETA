# SPDX-License-Identifier: AGPL-3.0-or-later
"""Outbound to DIAL (roadmap 4.3, ADR-0037): emergency broadcast (rings handsets, plays the text) and DECT text
messages, always through the outbox with retries; each call is a ``Broadcast`` row (the delivery report).

- Evacuation: a webhook sink listens to ``evacuation.state_changed``; raising or escalating into a stage listed in
  the link settings (drills only when allowed) and the all clear ring DIAL handsets with the stage's spoken text.
- Announcements: two channels, ``dial_call`` (emergency broadcast, for urgent levels) and ``dial_sms`` (DECT text
  message). DIAL's emergency broadcast also sends the text as a DECT message when its messaging feature is on, so
  EVAC never sends both for the same alarm.
"""
from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import outbox

from . import link
from .client import Client, Rejected
from .models import Broadcast

log = logging.getLogger("evac.dial")

JOB = "dial.broadcast"
SMS_LIMIT = 480
RAISING = {"raise", "escalate", "replace_drill"}


def config_for(event: Any) -> Any:
    from apps.extensions import services as ext

    return ext.effective(link.KEY, event) if event is not None else None


def queue(config: Any, *, kind: str, source: str, text: str, reference: str = "", group: str = "",
          enqueue: bool = True) -> Broadcast | None:
    """Create the broadcast row and (``enqueue``) its outbox job, once per ``reference``."""
    text = (text or "").strip()
    if not text:
        return None
    if kind == Broadcast.Kind.MESSAGE:
        text = text[:SMS_LIMIT]
    if reference:
        old = Broadcast.objects.filter(config=config, kind=kind, source=source, reference=reference[:100]).first()
        if old is not None:
            return old
    b = Broadcast.objects.create(config=config, event=config.event, kind=kind, source=source,
                                 reference=reference[:100], text=text, group=group[:80])
    if enqueue:
        outbox.enqueue(JOB, {"broadcast": str(b.pk)}, event=config.event, key=f"dial-broadcast:{b.pk}")
    return b


def send(b: Broadcast) -> dict[str, Any]:
    """One call to DIAL. ``Rejected`` marks the broadcast failed at once; ``Temporary`` propagates (outbox retry)."""
    client = Client.for_config(b.config)
    if b.kind == Broadcast.Kind.EMERGENCY:
        path, body = "emergency/broadcast/", {"event": client.event, "announcement": b.text}
    else:
        path, body = "messaging/broadcast/", {"event": client.event, "text": b.text[:SMS_LIMIT]}
    if b.group:
        body["group"] = b.group
    b.attempts += 1
    try:
        data = client.post(path, body) or {}
    except Rejected as exc:
        b.status, b.detail = Broadcast.Status.FAILED, str(exc)[:500]
        b.save(update_fields=["status", "detail", "attempts"])
        return {"status": "failed", "detail": b.detail}
    except Exception as exc:
        b.detail = f"{type(exc).__name__}: {exc}"[:500]
        b.save(update_fields=["detail", "attempts"])
        raise
    results = data.get("results") if isinstance(data.get("results"), dict) else {}
    if b.kind == Broadcast.Kind.EMERGENCY:
        b.targets = int(data.get("targets") or 0)
        b.detail = (_("%(n)s handsets rung") % {"n": b.targets}) + (
            f" · PBX: {results['error']}" if results.get("error") else "") + (
            _(" · text message sent") if results.get("text_broadcast") else "")
    else:
        b.targets = int(data.get("sent_count") or 0)
        b.detail = _("%(n)s sent, %(f)s failed") % {"n": b.targets, "f": int(data.get("failed_count") or 0)}
    b.status = Broadcast.Status.FAILED if results.get("error") and not b.targets else Broadcast.Status.SENT
    b.response = {"id": data.get("id"), "targets": b.targets, "error": str(results.get("error") or "")[:300],
                  "text_broadcast": results.get("text_broadcast")}
    b.sent_at = timezone.now()
    b.save(update_fields=["status", "detail", "attempts", "targets", "response", "sent_at"])
    return {"status": "sent" if b.status == Broadcast.Status.SENT else "failed", "recipients": b.targets,
            "detail": b.detail}


def handle_job(job: Any) -> None:
    b = Broadcast.objects.select_related("config", "event").filter(pk=job.payload["broadcast"]).first()
    if b is None or b.status != Broadcast.Status.PENDING:
        job.result = {"skipped": "gone or done"}
        return
    job.result = send(b)


# ------------------------------------------------------------------ evacuation
def stage_text(event: Any, state: str, *, drill: bool, zone_name: str | None) -> str:
    """The stage's spoken text (Evacuation -> Screen content), else its first screen text, else the stage name."""
    from apps.evacuation import services
    from apps.evacuation.models import StageContent

    row = StageContent.objects.filter(event=event, state=state).first()
    text = ""
    if row is not None:
        text = row.speech_text.strip() or next((t.strip() for t in row.texts or [] if str(t).strip()), "")
    cfg = services.config(event)
    if not text:
        text = cfg.labels.get(state) or state.replace("_", " ").capitalize()
    if zone_name:
        text = f"{zone_name}: {text}"
    return f"{cfg.drill_text}: {text}" if drill else text


def on_evacuation(payload: dict[str, Any], event: Any) -> Broadcast | None:
    config = config_for(event)
    if config is None or not config.feature_enabled("evacuation_broadcast"):
        return None
    s = link.settings_of(config)
    state, kind, drill = payload.get("state"), payload.get("kind"), bool(payload.get("drill"))
    if drill and not s.get("broadcast_drills"):
        return None
    if state == "all_clear":
        if not s.get("broadcast_all_clear"):
            return None
        last = Broadcast.objects.filter(config=config, source=Broadcast.Source.EVACUATION).order_by(
            "-created_at").first()
        if last is None or last.reference.endswith(":all_clear"):
            return None  # nothing was rung for this alarm
    elif state not in (s.get("broadcast_states") or []) or kind not in RAISING:
        return None
    text = stage_text(event, str(state), drill=drill, zone_name=payload.get("zone_name"))
    ref = f"{payload.get('zone') or 'event'}:{payload.get('version')}:{state}"
    return queue(config, kind=Broadcast.Kind.EMERGENCY, source=Broadcast.Source.EVACUATION, text=text,
                 reference=ref, group=str(s.get("broadcast_group") or ""))


def sink(event_type: str, payload: dict[str, Any], event: Any) -> None:
    if event_type != "evacuation.state_changed" or event is None:
        return
    try:
        on_evacuation(payload, event)
    except Exception:  # an integration must never break the evacuation change itself
        log.exception("DIAL evacuation broadcast could not be queued")


# ------------------------------------------------------------------ announcement channels
def available(event: Any) -> bool:
    config = config_for(event)
    return config is not None and config.feature_enabled("announcements")


def channel(kind: str) -> Any:
    def send_delivery(d: Any) -> dict[str, Any]:
        from apps.announcements.services import text_for

        ann = d.announcement
        config = config_for(ann.event)
        if config is None or not config.feature_enabled("announcements"):
            return {"status": "skipped", "detail": _("DIAL is not linked for this event.")}
        key = "dial_call" if kind == Broadcast.Kind.EMERGENCY else "dial_sms"
        text = text_for(ann, key, SMS_LIMIT if kind == Broadcast.Kind.MESSAGE else 1000)
        # sent inside the announcement's own outbox job: its retries resend this row
        b = queue(config, kind=kind, source=Broadcast.Source.ANNOUNCEMENT, text=text, reference=f"delivery:{d.pk}",
                  group=str(link.settings_of(config).get("broadcast_group") or "") if kind == Broadcast.Kind.EMERGENCY
                  else "", enqueue=False)
        if b is None:
            return {"status": "skipped", "detail": _("Nothing to say.")}
        if b.status == Broadcast.Status.PENDING:
            return send(b)
        return {"status": b.status, "recipients": b.targets, "detail": b.detail}
    return send_delivery
