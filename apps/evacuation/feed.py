# SPDX-License-Identifier: AGPL-3.0-or-later
"""What every screen shows during an evacuation, and pushing it (ADR-0033, ADR-0034).

Each screen gets its own *evacuation payload*: the state it shows (event and its zones, highest severity wins),
the drill marker, the stage's texts, layout, sound and spoken message, its role and its direction. Payloads carry
the event's message sequence number ``seq`` (monotonic, persisted) and a content version ``v``; the player keeps
the newest one and acknowledges what it rendered. Every change of state, blocked points, stage content or the
relevant settings pushes new payloads to all screens of the event at once (``evac.state`` message) and screens
also fetch theirs on start and reconnect (``/player/api/evacuation/state/``).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from . import guidance, machine, services
from .machine import Model, State
from .models import EventAlarm, StageContent

DEFAULT_TEXTS: dict[str, list[str]] = {
    "attention": ["Attention please. Follow the announcements and the instructions of the staff."],
    "shelter_in_place": ["Stay inside. Move away from windows and doors.",
                         "Follow the instructions of the staff."],
    "evacuate": ["Leave the building now by the nearest exit.", "Do not use the lifts.",
                 "Follow the signs and the staff."],
    "all_clear": ["All clear. Thank you."],
    "staff_alert": [],
    "normal": [],
}
DEFAULT_SOUND = {"evacuate": "siren", "shelter_in_place": "alert", "attention": "gong"}
#: stages that take over participating screens (attention is a banner over the normal content)
TAKEOVER = frozenset({State.SHELTER, State.EVACUATE, State.ALL_CLEAR})


def bump(event: Any) -> int:
    """Next message number of the event (monotonic, survives restarts; ADR-0003)."""
    EventAlarm.objects.get_or_create(event=event)
    EventAlarm.objects.filter(event=event).update(seq=F("seq") + 1, seq_at=timezone.now())
    return int(EventAlarm.objects.values_list("seq", flat=True).get(event=event))


def current_seq(event: Any) -> int:
    row = EventAlarm.objects.filter(event=event).values_list("seq", flat=True).first()
    return int(row or 0)


def stage_content(event: Any, state: str) -> dict[str, Any]:
    row = StageContent.objects.filter(event=event, state=state).first()
    texts = [t for t in (row.texts if row else []) if t] or DEFAULT_TEXTS.get(state, [])
    sound = row.sound if row else DEFAULT_SOUND.get(state, "none")
    return {"layout_id": str(row.layout_id) if row and row.layout_id else None, "texts": texts,
            "rotate_seconds": row.rotate_seconds if row else 8, "pictograms_only": bool(row and row.pictograms_only),
            "sound": sound, "sound_every": row.sound_every if row else 30,
            "speech": row.speech_file if row and row.speech_status == "ready" else ""}


def layout_data(layout_id: str | None) -> dict[str, Any] | None:
    """The published version of a content layout, or None (the player then uses the built-in fallback)."""
    if not layout_id:
        return None
    from django.apps import apps

    if not apps.is_installed("apps.content"):
        return None
    from apps.content.models import Layout

    layout = Layout.objects.filter(pk=layout_id).select_related("published").first()
    if layout is None or layout.published is None:
        return None
    data: dict[str, Any] = layout.published.data
    return data


def _role(screen: Any) -> str:
    try:
        from apps.screens import display

        return str(display.for_screen(screen).get("evacuation_role") or "participant")
    except Exception:  # noqa: BLE001 - a broken setting must never keep a screen out of an evacuation
        return "participant"


def payloads(event: Any, screens: list[Any] | None = None, *, seq: int | None = None) -> dict[str, dict[str, Any]]:
    """Payload per screen id. ``screens`` limits the work (default: all screens of the event)."""
    from apps.venues.models import Point

    cfg = services.config(event)
    seq = current_seq(event) if seq is None else seq
    views = services.screen_views(event)
    if screens is not None:
        wanted = {str(s.pk) for s in screens}
        views = [v for v in views if str(v.screen.pk) in wanted]
    contents: dict[str, dict[str, Any]] = {}
    layouts: dict[str, dict[str, Any] | None] = {}
    ids = {v.guidance.toward for v in views} | {v.guidance.target for v in views}
    names = {str(p.pk): p.name for p in Point.objects.filter(pk__in=[i for i in ids if i])}
    out: dict[str, dict[str, Any]] = {}
    now = timezone.now()
    for view in views:
        shown = machine.current(view.shown, now)
        state = shown.state.value
        if state not in contents:
            contents[state] = stage_content(event, state)
            layouts[state] = layout_data(contents[state]["layout_id"])
        content = contents[state]
        g = view.guidance
        direction = g.text or names.get(g.target or "", "")
        body: dict[str, Any] = {
            "event": event.slug, "screen": str(view.screen.pk), "seq": seq, "state": state,
            "label": cfg.labels.get(state, state), "drill": shown.drill, "drill_text": cfg.drill_text,
            "since": shown.since.isoformat() if shown.since else None,
            "clear_until": shown.clear_until.isoformat() if shown.clear_until else None,
            "takeover": shown.state in TAKEOVER, "role": _role(view.screen), "model": cfg.model.value,
            "guidance": {"kind": g.kind.value, "arrow": g.arrow.value if g.arrow else None, "text": g.text,
                         "toward": names.get(g.toward or "", ""), "target": names.get(g.target or "", ""),
                         "distance": g.distance},
            "direction": direction if g.kind in (guidance.Kind.ROUTE, guidance.Kind.HINT) else "",
            "texts": content["texts"], "rotate_seconds": content["rotate_seconds"],
            "pictograms_only": content["pictograms_only"], "sound": content["sound"],
            "sound_every": content["sound_every"], "speech": speech_url(content["speech"], view.screen),
            "layout": layouts[state],
        }
        body["v"] = hashlib.sha256(json.dumps({k: v for k, v in body.items() if k != "seq"}, sort_keys=True,
                                              default=str).encode()).hexdigest()[:16]
        out[str(view.screen.pk)] = body
    return out


def speech_url(name: str, screen: Any) -> str:
    if not name:
        return ""
    from django.core import signing
    from django.urls import reverse

    sig = signing.Signer(salt="evac-speech").signature(f"{screen.pk}:{name}")
    return f"{reverse('evacuation_player:speech', args=[name])}?s={screen.pk}.{sig}"


def push(event: Any) -> None:
    """Bump ``seq`` now (in the change's transaction, so every signed message after it is newer) and, after the
    commit, send every screen of the event its payload."""
    seq = bump(event)

    def send() -> None:
        import time

        from django.apps import apps

        if not apps.is_installed("apps.screens"):
            return
        from apps.screens import channel

        if current_seq(event) != seq:
            return  # a newer change is on its way and sends its own payloads
        issued = int(time.time() * 1000)
        for sid, body in payloads(event, seq=seq).items():
            body["issued"] = issued
            screen = _screen(sid)
            if screen is not None:
                channel.send(screen, "evac.state", sign(event, body))

    transaction.on_commit(send)


def _screen(sid: str) -> Any:
    from apps.screens.models import Screen

    return Screen.objects.paired().filter(pk=sid).first()


def sign(event: Any, body: dict[str, Any]) -> dict[str, Any]:
    """Attach the alarm signature (ADR-0034)."""
    from . import alarmkey

    return alarmkey.sign_payload(event, body)


#: at most this many precomputed direction variants (one per blocked exit or assembly point) per screen
MAX_VARIANTS = 30
BUNDLE_STAGES = (State.ATTENTION, State.SHELTER, State.EVACUATE, State.ALL_CLEAR)


def _direction(g: guidance.Guidance, names: dict[str, str]) -> dict[str, Any]:
    return {"kind": g.kind.value, "arrow": g.arrow.value if g.arrow else None, "text": g.text,
            "target": names.get(g.target or "", ""), "direction": g.text or names.get(g.target or "", "")}


def bundle(screen: Any) -> dict[str, Any]:
    """Everything a screen needs to show every stage without the server (ADR-0034, brief §8.6)."""
    from apps.core import settings_store
    from apps.venues.models import Point

    from . import alarmkey

    event = screen.event
    cfg = services.config(event)
    stages: dict[str, Any] = {}
    for state in BUNDLE_STAGES:
        if state not in cfg.enabled:
            continue
        c = stage_content(event, state.value)
        stages[state.value] = {"label": cfg.labels.get(state.value, state.value), "texts": c["texts"],
                               "rotate_seconds": c["rotate_seconds"], "pictograms_only": c["pictograms_only"],
                               "sound": c["sound"], "sound_every": c["sound_every"],
                               "speech": speech_url(c["speech"], screen), "layout": layout_data(c["layout_id"]),
                               "takeover": state in TAKEOVER}
    blocked = services.blocked_ids(event)
    views = services.screen_views(event, screens=[screen])
    zone_ids = views[0].zone_ids if views else []
    directions: dict[str, Any] = {}
    names = {str(p.pk): p.name for p in Point.objects.filter(venue__events=event)}
    if views:
        directions[",".join(sorted(blocked))] = _direction(views[0].guidance, names)
        if cfg.model is Model.ZONES:
            targets = Point.objects.filter(venue__events=event, kind__in=("exit", "assembly")) \
                .exclude(pk__in=blocked).values_list("pk", flat=True)[:MAX_VARIANTS]
            for pid in targets:
                variant = blocked | {str(pid)}
                v = services.screen_views(event, blocked=variant, screens=[screen])
                directions[",".join(sorted(variant))] = _direction(v[0].guidance, names)
    origins = [str(o).rstrip("/") for o in settings_store.get("evacuation", event=event).get("fallback_origins") or []]
    body: dict[str, Any] = {
        "event": event.slug, "screen": str(screen.pk), "keys": alarmkey.public_keys(event),
        "drill_text": cfg.drill_text, "model": cfg.model.value, "role": _role(screen), "zones": zone_ids,
        "stages": stages, "directions": directions, "blocked": sorted(blocked), "fallback_origins": origins,
        "labels": cfg.labels,
    }
    body["version"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return body
