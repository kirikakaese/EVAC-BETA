# SPDX-License-Identifier: AGPL-3.0-or-later
"""Program services (ADR-0038): editing, live changes, imports with local overrides, what screens receive.

Every change is audited and, after the commit, pushed: ``schedule.changed`` to the event's screens (they refetch
``/player/api/schedule/``), the ``program.session_changed`` webhook/realtime event, and ``anchor_moved`` so
announcements timed relative to a session follow it (ADR-0025).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import settings_store, webhooks
from apps.core.audit import log

from .models import Session, SessionChange, Speaker, Stage, Track

ANCHOR_KEY = "program"
PUSH = "schedule.changed"
WEBHOOK = "program.session_changed"


def program_settings(event: Any) -> dict[str, Any]:
    return settings_store.get("program", event=event)


def ensure_local(event: Any) -> None:
    """Live changes belong to the venue node while the event is checked out (ADR-0036)."""
    from apps.nodes import guard

    try:
        guard.ensure_local(event)
    except guard.CheckedOut as exc:
        raise ValidationError(str(exc)) from None


# ------------------------------------------------------------------ push
def payload_of(s: Session) -> dict[str, Any]:
    return {"id": str(s.pk), "event": s.event.slug, "title": s.title, "stage": s.stage.name if s.stage_id else None,
            "starts_at": s.starts_at.isoformat(), "ends_at": s.ends_at.isoformat(), "status": s.status,
            "delay_minutes": s.delay_minutes, "moved": s.moved, "note": s.note}


def notify(event: Any, sessions: list[Session] | None = None) -> None:
    """After the commit: screens refetch, integrations hear about it, anchored announcements follow."""
    sessions = list(sessions or [])

    def run() -> None:
        from apps.core.signals import anchor_moved

        push_screens(event)
        for s in sessions:
            webhooks.emit(WEBHOOK, payload_of(s), event=event)
            anchor_moved.send(sender=ANCHOR_KEY, event=event, anchor_id=str(s.pk))
    transaction.on_commit(run)


def push_screens(event: Any) -> int:
    from django.apps import apps

    if not apps.is_installed("apps.screens"):
        return 0
    from apps.screens import channel
    from apps.screens.models import Screen

    ids = list(Screen.objects.paired().filter(event=event).values_list("pk", flat=True))
    return channel.send_many([(sid, PUSH, {}) for sid in ids]) if ids else 0


# ------------------------------------------------------------------ editing
def _validate(s: Session) -> None:
    if not s.title.strip():
        raise ValidationError(_("A title is needed."))
    if s.ends_at <= s.starts_at:
        raise ValidationError(_("The end must be after the start."))
    if s.stage_id and s.stage.event_id != s.event_id:
        raise ValidationError(_("The stage belongs to another event."))
    if s.track_id and s.track.event_id != s.event_id:
        raise ValidationError(_("The track belongs to another event."))


def save_session(s: Session, *, actor: Any, request: Any = None, speakers: list[Speaker] | None = None,
                 changed: list[str] | None = None) -> Session:
    """Create or edit (the edit form). For imported sessions the ``changed`` fields become local overrides."""
    _validate(s)
    created = s._state.adding
    if not created and s.source:
        s.overrides = sorted(set(s.overrides or []) | {f for f in (changed or []) if f in Session.IMPORTED})
    if not created:
        s.version += 1
    with transaction.atomic():
        s.save()
        if speakers is not None:
            s.speakers.set(speakers)
        if created:
            SessionChange.objects.create(session=s, event=s.event, kind=SessionChange.Kind.NEW, actor=_user(actor),
                                         text=_("%(t)s added") % {"t": s.title})
    log(action="program.session_created" if created else "program.session_edited", actor=actor, target=s,
        event=s.event, request=request, message=f"Session {s.title}",
        changes={"changed": changed or [], "overrides": s.overrides})
    notify(s.event, [s])
    return s


def delete_session(s: Session, *, actor: Any, request: Any = None) -> None:
    event = s.event
    log(action="program.session_deleted", actor=actor, target=s, event=event, request=request,
        message=f"Session {s.title} deleted")
    s.delete()
    notify(event)


def _user(actor: Any) -> Any:
    return actor if getattr(actor, "pk", None) and getattr(actor, "is_authenticated", True) else None


def _remember_plan(s: Session) -> None:
    if s.planned_start is None:
        s.planned_start, s.planned_end = s.starts_at, s.ends_at
    if s.planned_stage_id is None and s.stage_id:
        s.planned_stage_id = s.stage_id


def _live(s: Session, kind: str, text: str, *, actor: Any, request: Any, fields: list[str], note: str = "",
          data: dict[str, Any] | None = None) -> Session:
    ensure_local(s.event)
    if note is not None:
        s.note = note[:200]
    if s.source:
        s.overrides = sorted(set(s.overrides or []) | (set(fields) & set(Session.IMPORTED)))
    s.version += 1
    _validate(s)
    with transaction.atomic():
        s.save()
        SessionChange.objects.create(session=s, event=s.event, kind=kind, text=text[:300], data=data or {},
                                     actor=_user(actor))
    log(action=f"program.{kind}", actor=actor, target=s, event=s.event, request=request, message=text,
        changes={"starts_at": s.starts_at.isoformat(), "ends_at": s.ends_at.isoformat(),
                 "stage": s.stage.name if s.stage_id else None, "status": s.status, **(data or {})})
    notify(s.event, [s])
    return s


def _hm(value: dt.datetime, event: Any) -> str:
    import zoneinfo

    try:
        tz = zoneinfo.ZoneInfo(event.timezone or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        tz = dt.UTC
    return value.astimezone(tz).strftime("%H:%M")


def delay(s: Session, minutes: int, *, actor: Any, request: Any = None, note: str | None = None,
          shift_following: bool = False) -> Session:
    """Shift the session (positive: later). ``shift_following`` moves the later sessions on the same stage that
    day by the same amount."""
    minutes = int(minutes)
    if not minutes or abs(minutes) > 24 * 60:
        raise ValidationError(_("Give a delay in minutes (at most a day)."))
    _remember_plan(s)
    delta = dt.timedelta(minutes=minutes)
    s.starts_at, s.ends_at = s.starts_at + delta, s.ends_at + delta
    kind = SessionChange.Kind.DELAY if s.starts_at >= (s.planned_start or s.starts_at) else SessionChange.Kind.EARLIER
    if s.delay_minutes == 0:
        kind = SessionChange.Kind.RESTORE
    if note is None:
        note = "" if s.delay_minutes == 0 else (
            _("Starts %(n)s min late") % {"n": s.delay_minutes} if s.delay_minutes > 0
            else _("Starts %(n)s min early") % {"n": -s.delay_minutes})
    text = _("%(t)s now starts at %(h)s") % {"t": s.title, "h": _hm(s.starts_at, s.event)}
    out = _live(s, kind, text, actor=actor, request=request, fields=["starts_at", "ends_at"], note=note,
                data={"minutes": minutes})
    if shift_following and s.stage_id:
        day_end = s.starts_at.replace(hour=23, minute=59)
        for later in Session.objects.filter(event=s.event, stage=s.stage, status=Session.Status.SCHEDULED,
                                            starts_at__gt=s.starts_at - delta, starts_at__lte=day_end).exclude(pk=s.pk):
            delay(later, minutes, actor=actor, request=request)
    return out


def cancel(s: Session, *, actor: Any, request: Any = None, note: str | None = None) -> Session:
    if s.status == Session.Status.CANCELLED:
        raise ValidationError(_("Already cancelled."))
    _remember_plan(s)
    s.status = Session.Status.CANCELLED
    return _live(s, SessionChange.Kind.CANCEL, _("%(t)s is cancelled") % {"t": s.title}, actor=actor,
                 request=request, fields=["status"], note=_("Cancelled") if note is None else note)


def move(s: Session, stage: Stage | None, *, actor: Any, request: Any = None, note: str | None = None) -> Session:
    if stage is not None and stage.event_id != s.event_id:
        raise ValidationError(_("The stage belongs to another event."))
    if stage == s.stage:
        raise ValidationError(_("The session is already there."))
    _remember_plan(s)
    s.stage = stage
    where = stage.name if stage else _("no room")
    if note is None:
        note = _("Moved to %(r)s") % {"r": where}
    return _live(s, SessionChange.Kind.ROOM, _("%(t)s moved to %(r)s") % {"t": s.title, "r": where}, actor=actor,
                 request=request, fields=["stage"], note=note, data={"stage": where})


def reschedule(s: Session, starts_at: dt.datetime, ends_at: dt.datetime, *, actor: Any, request: Any = None,
               note: str | None = None) -> Session:
    _remember_plan(s)
    s.starts_at, s.ends_at = starts_at, ends_at
    text = _("%(t)s moved to %(h)s") % {"t": s.title, "h": _hm(starts_at, s.event)}
    return _live(s, SessionChange.Kind.TIME, text, actor=actor, request=request, fields=["starts_at", "ends_at"],
                 note=(_("New time: %(h)s") % {"h": _hm(starts_at, s.event)}) if note is None else note)


def restore(s: Session, *, actor: Any, request: Any = None) -> Session:
    """Back to the plan: original time and stage, not cancelled, no note."""
    if not s.changed and not s.note:
        raise ValidationError(_("Nothing to undo."))
    if s.planned_start is not None:
        s.starts_at, s.ends_at = s.planned_start, s.planned_end or s.ends_at
    if s.planned_stage_id:
        s.stage_id = s.planned_stage_id
    s.status = Session.Status.SCHEDULED
    s.planned_start = s.planned_end = None
    s.planned_stage = None
    # the plan is the source's: the next sync may move or cancel it again
    s.overrides = [f for f in (s.overrides or []) if f not in ("starts_at", "ends_at", "stage", "status")]
    return _live(s, SessionChange.Kind.RESTORE, _("%(t)s is back to plan") % {"t": s.title}, actor=actor,
                 request=request, fields=[], note="")


def reset_overrides(s: Session, *, actor: Any, request: Any = None) -> Session:
    """Forget local changes of an imported session; the next sync writes the source's values again."""
    s.overrides = []
    s.save(update_fields=["overrides", "updated_at"])
    log(action="program.overrides_reset", actor=actor, target=s, event=s.event, request=request,
        message=f"Session {s.title} follows its source again")
    return s


# ------------------------------------------------------------------ import
@dataclass
class Imported:
    """One session as a source (pretalx, frab, iCal) describes it."""

    external_id: str
    title: str
    starts_at: dt.datetime
    ends_at: dt.datetime
    stage: str = ""
    track: str = ""
    subtitle: str = ""
    abstract: str = ""
    language: str = ""
    kind: str = ""
    url: str = ""
    speakers: list[tuple[str, str]] = field(default_factory=list)  # (external id or "", name)
    cancelled: bool = False


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    kept_local: int = 0  # fields that kept their local value
    missing: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (_("%(c)s new, %(u)s updated, %(n)s unchanged, %(m)s gone from the source, %(k)s local changes kept")
                % {"c": self.created, "u": self.updated, "n": self.unchanged, "m": self.missing + self.removed,
                   "k": self.kept_local})


def _stage_for(event: Any, name: str, source: str, cache: dict[str, Stage]) -> Stage | None:
    name = (name or "").strip()[:120]
    if not name:
        return None
    if name not in cache:
        from apps.venues.models import Room

        stage = Stage.objects.filter(event=event, name=name).first()
        if stage is None:
            room = Room.objects.filter(venue__in=event.venues.all(), name__iexact=name).first()
            stage = Stage.objects.create(event=event, name=name, room=room, source=source,
                                         order=Stage.objects.filter(event=event).count())
        cache[name] = stage
    return cache[name]


def _track_for(event: Any, name: str, cache: dict[str, Track]) -> Track | None:
    name = (name or "").strip()[:120]
    if not name:
        return None
    if name not in cache:
        cache[name] = Track.objects.get_or_create(event=event, name=name)[0]
    return cache[name]


def _speakers_for(event: Any, people: list[tuple[str, str]], source: str) -> list[Speaker]:
    out = []
    for ext, name in people:
        name = (name or "").strip()[:200]
        if not name:
            continue
        sp = None
        if ext:
            sp = Speaker.objects.filter(event=event, source=source, external_id=ext[:200]).first()
        sp = sp or Speaker.objects.filter(event=event, name=name).first()
        if sp is None:
            sp = Speaker.objects.create(event=event, name=name, source=source, external_id=(ext or "")[:200])
        out.append(sp)
    return out


def merge(event: Any, source: str, items: list[Imported], *, actor: Any = None) -> ImportResult:
    """Bring the event's sessions from ``source`` in line with ``items``. Fields listed in a session's
    ``overrides`` keep their local value; sessions the source no longer has are deleted, unless they were changed
    here (then they stay, flagged ``missing_upstream``)."""
    res = ImportResult()
    stages: dict[str, Stage] = {}
    tracks: dict[str, Track] = {}
    seen: set[str] = set()
    touched: list[Session] = []
    with transaction.atomic():
        existing = {s.external_id: s for s in Session.objects.filter(event=event, source=source)}
        for it in items:
            ext = (it.external_id or "").strip()[:200]
            if not ext or ext in seen or it.ends_at <= it.starts_at:
                if ext not in seen:
                    res.errors.append(f"{it.title or ext}: skipped (no id or no duration)")
                continue
            seen.add(ext)
            values: dict[str, Any] = {
                "title": it.title.strip()[:300] or ext, "subtitle": it.subtitle[:300], "abstract": it.abstract,
                "language": it.language[:20], "kind": it.kind[:60], "url": it.url[:500],
                "stage": _stage_for(event, it.stage, source, stages), "track": _track_for(event, it.track, tracks),
                "starts_at": it.starts_at, "ends_at": it.ends_at}
            speakers = _speakers_for(event, it.speakers, source)
            s = existing.get(ext)
            if s is None:
                s = Session(event=event, source=source, external_id=ext, **values,
                            status=Session.Status.CANCELLED if it.cancelled else Session.Status.SCHEDULED)
                s.save()
                s.speakers.set(speakers)
                res.created += 1
                touched.append(s)
                continue
            keep = set(s.overrides or [])
            changed = False
            for name, value in values.items():
                current = getattr(s, name)
                if current == value or (name in ("stage", "track") and getattr(current, "pk", None) ==
                                        getattr(value, "pk", None)):
                    continue
                if name in keep or (name in ("starts_at", "ends_at") and s.planned_start is not None) or (
                        name == "stage" and s.planned_stage_id):
                    res.kept_local += 1
                    continue
                setattr(s, name, value)
                changed = True
            if "speakers" not in keep and {p.pk for p in s.speakers.all()} != {p.pk for p in speakers}:
                s.speakers.set(speakers)
                changed = True
            want = Session.Status.CANCELLED if it.cancelled else Session.Status.SCHEDULED
            if s.status != want and "status" not in keep:
                s.status = want
                changed = True
            if s.missing_upstream:
                s.missing_upstream = False
                changed = True
            if changed:
                s.version += 1
                s.save()
                res.updated += 1
                touched.append(s)
            else:
                res.unchanged += 1
        for ext, s in existing.items():
            if ext in seen:
                continue
            if s.overrides or s.planned_start is not None or s.planned_stage_id or s.note:
                if not s.missing_upstream:
                    s.missing_upstream = True
                    s.save(update_fields=["missing_upstream", "updated_at"])
                res.missing += 1
            else:
                s.delete()
                res.removed += 1
    log(action="program.imported", actor=actor, event=event, message=f"Program import from {source}: "
        f"{res.summary()}", scope={"source": source},
        changes={"created": res.created, "updated": res.updated, "missing": res.missing, "removed": res.removed,
                 "kept_local": res.kept_local})
    if res.created or res.updated or res.removed or res.missing:
        notify(event, touched[:200])
    return res


# ------------------------------------------------------------------ reading
def window(event: Any, start: dt.datetime, end: dt.datetime, *, public_only: bool = False) -> Any:
    qs = (Session.objects.filter(event=event, ends_at__gt=start, starts_at__lt=end)
          .select_related("stage", "track", "planned_stage").prefetch_related("speakers"))
    return qs.filter(public=True) if public_only else qs


def session_data(s: Session) -> dict[str, Any]:
    return {"id": str(s.pk), "title": s.title, "subtitle": s.subtitle, "start": s.starts_at.isoformat(),
            "end": s.ends_at.isoformat(), "stage": str(s.stage_id) if s.stage_id else None,
            "stage_name": s.stage.name if s.stage_id else "", "track": s.track.name if s.track_id else "",
            "colour": s.track.colour if s.track_id else "", "speakers": [p.name for p in s.speakers.all()],
            "status": s.status, "delay": s.delay_minutes, "moved_from": s.planned_stage.name if s.moved and
            s.planned_stage_id else "", "planned_start": s.planned_start.isoformat() if s.planned_start else None,
            "note": s.note, "language": s.language, "kind": s.kind}


def screen_payload(event: Any, now: dt.datetime | None = None, *, hours_back: int = 12,
                   hours_ahead: int = 48) -> dict[str, Any]:
    """What a screen keeps: sessions around now (it computes now/next itself, also offline), stages, changes."""
    now = now or timezone.now()
    sessions = window(event, now - dt.timedelta(hours=hours_back), now + dt.timedelta(hours=hours_ahead),
                      public_only=True)
    stages = Stage.objects.filter(event=event)
    hours = int(program_settings(event).get("changes_hours") or 6)
    changes = SessionChange.objects.filter(event=event, at__gte=now - dt.timedelta(hours=hours),
                                           session__public=True).exclude(kind=SessionChange.Kind.NEW)[:20]
    return {"event": event.slug, "timezone": event.timezone, "generated": now.isoformat(),
            "stages": [{"id": str(st.pk), "name": st.name, "room": str(st.room_id) if st.room_id else None}
                       for st in stages],
            "sessions": [session_data(s) for s in sessions],
            "changes": [{"text": c.text, "kind": c.kind, "at": c.at.isoformat(), "session": str(c.session_id)}
                        for c in changes]}


def now_next(event: Any, stage: Stage, now: dt.datetime | None = None) -> tuple[Session | None, Session | None]:
    now = now or timezone.now()
    qs = Session.objects.filter(event=event, stage=stage, status=Session.Status.SCHEDULED, ends_at__gt=now)
    current = qs.filter(starts_at__lte=now).order_by("starts_at").first()
    upcoming = qs.filter(starts_at__gt=now).order_by("starts_at").first()
    return current, upcoming


# ------------------------------------------------------------------ anchors (ADR-0025)
def anchor_choices(event: Any) -> list[tuple[str, str]]:
    now = timezone.now()
    out = []
    for s in (Session.objects.filter(event=event, ends_at__gt=now, starts_at__lt=now + dt.timedelta(days=14))
              .exclude(status=Session.Status.CANCELLED).select_related("stage")[:300]):
        out.append((str(s.pk), f"{timezone.localtime(s.starts_at):%a %H:%M} · {s.evac_anchor_label()}"))
    return out


def anchor_resolve(event: Any, anchor_id: str) -> Any:
    from apps.core.plugins import Anchor

    try:
        s = Session.objects.select_related("stage").filter(event=event, pk=anchor_id).first()
    except (ValueError, ValidationError):
        return None
    if s is None or s.status == Session.Status.CANCELLED:
        return None
    return Anchor(start=s.starts_at, end=s.ends_at, label=s.evac_anchor_label())
