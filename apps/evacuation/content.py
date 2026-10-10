# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stage content (texts, layout, sound, spoken message) and the layout guardrails hook (ADR-0033)."""
from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _

from apps.core import audit, settings_store

from . import feed, lint, services
from .machine import Model, State
from .models import StageContent

STAGES = (State.ATTENTION, State.SHELTER, State.EVACUATE, State.ALL_CLEAR)
SPEECH_JOB = "evacuation.speech"


def layouts_of(event: Any) -> list[Any]:
    from django.apps import apps

    if not apps.is_installed("apps.content"):
        return []
    from django.db.models import Q

    from apps.content.models import Layout

    return list(Layout.objects.filter(Q(event=event) | Q(event__isnull=True)).order_by("name"))


def _tokens(event: Any, layout: Any) -> dict[str, Any]:
    try:
        from apps.content import services as content

        return dict(content.resolved_tokens(getattr(layout, "theme", None) or content.event_theme(event)))
    except Exception:  # noqa: BLE001 - without theme data the check falls back to "check contrast yourself"
        return {}


def findings(event: Any, layout: Any, data: Any) -> list[lint.Finding]:
    cfg = services.config(event)
    s = settings_store.get("evacuation", event=event)
    return lint.lint(data or {}, zones_model=cfg.model is Model.ZONES, tokens=_tokens(event, layout),
                     viewing_distance_m=float(s.get("viewing_distance_m") or 8),
                     screen_height_m=float(s.get("screen_height_m") or 0.6))


def layout_check(layout: Any, data: Any) -> list[dict[str, Any]]:
    """Registered layout check: guardrails for layouts used by an evacuation stage of their event."""
    from apps.core import modules
    from apps.events.models import Event

    rows = StageContent.objects.filter(layout_id=layout.pk)
    if layout.event_id:
        rows = rows.filter(event_id=layout.event_id)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows.select_related("event"):
        event: Event = row.event
        if not modules.is_enabled("evacuation", event):
            continue
        for f in findings(event, layout, data):
            key = f"{f.code}:{f.element}"
            if key not in seen:
                seen.add(key)
                out.append({**f.as_dict(), "message": f"{_('Evacuation')}: {f.message}"})
    return out


def save(event: Any, state: str, *, layout: Any, texts: list[str], rotate_seconds: int, pictograms_only: bool,
         sound: str, sound_every: int, speech_text: str, actor: Any = None, request: Any = None) -> StageContent:
    """Save a stage's content. A layout with guardrail errors is refused (``ValueError`` with the reasons)."""
    if layout is not None:
        data = layout.published.data if layout.published_id else layout.data
        errors = [f.message for f in findings(event, layout, data) if f.level == "error"]
        if errors:
            raise ValueError(" ".join(errors))
    row: StageContent = StageContent.objects.get_or_create(event=event, state=state)[0]
    before = {"layout": str(row.layout_id or ""), "texts": row.texts, "sound": row.sound,
              "speech_text": row.speech_text}
    row.layout_id = layout.pk if layout is not None else None
    row.texts = [t.strip()[:300] for t in texts if t.strip()][:12]
    row.rotate_seconds = max(3, min(int(rotate_seconds), 120))
    row.pictograms_only, row.sound, row.sound_every = pictograms_only, sound, max(5, min(int(sound_every), 600))
    speech_changed = speech_text.strip() != row.speech_text
    row.speech_text = speech_text.strip()[:500]
    if speech_changed:
        row.speech_file, row.speech_status, row.speech_detail = "", "", ""
    row.save()
    audit.log(action="evacuation.content_saved", actor=actor, event=event, target=row, request=request,
              message=f"{state} content", changes={"before": [before, None]})
    if speech_changed and row.speech_text:
        request_speech(row)
    feed.push(event)
    return row


def tts_available() -> bool:
    from django.apps import apps

    if not apps.is_installed("apps.announcements"):
        return False
    from apps.announcements import tts

    ok, _detail = tts.status()
    return bool(ok)


def request_speech(row: StageContent) -> None:
    from apps.core import outbox

    row.speech_status = "pending"
    row.save(update_fields=["speech_status"])
    outbox.enqueue(SPEECH_JOB, {"content": str(row.pk)}, event=row.event, key=f"evac-speech:{row.pk}:{row.speech_text}")


def render_speech(job: Any) -> None:
    """Outbox handler: pre-render the spoken message with Piper (announcements module, ADR-0022)."""
    row = StageContent.objects.select_related("event").filter(pk=job.payload.get("content")).first()
    if row is None or not row.speech_text:
        job.result = {"skipped": True}
        return
    from django.apps import apps

    if not apps.is_installed("apps.announcements"):
        StageContent.objects.filter(pk=row.pk).update(speech_status="failed",
                                                      speech_detail="announcements module not installed")
        return
    from apps.announcements import tts

    try:
        name = tts.render(row.speech_text)
    except tts.SpeechError as exc:
        StageContent.objects.filter(pk=row.pk).update(speech_status="failed", speech_detail=str(exc)[:300])
        job.result = {"error": str(exc)[:300]}
        return
    StageContent.objects.filter(pk=row.pk).update(speech_file=name, speech_status="ready", speech_detail="")
    job.result = {"file": name}
    feed.push(row.event)
