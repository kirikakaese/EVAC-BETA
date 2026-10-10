# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engelsystem import (roadmap 7.1, ADR-0041): angel types become teams, shifts become shifts (one per angel type
they need), shift entries become sign-ups.

Engelsystem API v0-beta (``<url>/api/v0-beta``, ``Authorization: Bearer <API key>``): ``/angeltypes`` and
``/angeltypes/{id}/shifts``; lists are wrapped in ``{"data": [...]}``. Shifts carry ``id``, ``name``,
``starts_at``, ``ends_at``, ``location {name}``, ``shift_type {name}`` and ``needed_angel_types`` with
``angel_type``, ``needs`` and ``entries [{user {id, name}}]``.

Local data wins: check-ins, no-shows and people added in EVAC stay; a shift that disappeared upstream is deleted
unless someone already checked in.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from apps.core import outbox, safefetch
from apps.core.plugins import ConnectionResult

KEY = "engelsystem"
JOB = "engelsystem.sync"


class SyncError(ValueError):
    pass


def source_of(config: Any) -> str:
    return f"{KEY}:{config.pk}"


def _base(config: Any) -> str:
    url = str((config.settings or {}).get("base_url") or "").rstrip("/")
    if not url:
        raise SyncError(_("No Engelsystem URL configured."))
    return url if url.endswith("/api/v0-beta") else f"{url}/api/v0-beta"


def _get(config: Any, path: str) -> Any:
    token = config.secret("api_key")
    try:
        got = safefetch.get(f"{_base(config)}{path}", headers={"Authorization": f"Bearer {token}"} if token else {},
                            allow_private=bool(getattr(settings, "EVAC_IMPORT_ALLOW_PRIVATE", False)),
                            max_bytes=20 * 1024 * 1024)
    except safefetch.FetchError as exc:
        raise SyncError(str(exc)) from None
    try:
        doc = json.loads(got.body)
    except ValueError:
        raise SyncError(_("Engelsystem did not answer with JSON (is the URL right?).")) from None
    return doc.get("data", doc) if isinstance(doc, dict) else doc


def fetch(config: Any) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], dict[str, Any]]]]:
    """``(angel types, [(angel type, shift)])`` of the selected angel types."""
    wanted = {str(x).strip().lower() for x in (config.settings or {}).get("angeltypes") or [] if str(x).strip()}
    types = [t for t in _get(config, "/angeltypes") or [] if isinstance(t, dict) and t.get("id") is not None]
    if wanted:
        types = [t for t in types if str(t.get("name", "")).lower() in wanted or str(t["id"]) in wanted]
    shifts = []
    for t in types:
        for s in _get(config, f"/angeltypes/{t['id']}/shifts") or []:
            if isinstance(s, dict):
                shifts.append((t, s))
    return types, shifts


def _when(value: Any) -> dt.datetime | None:
    d = parse_datetime(str(value or ""))
    return d if d is None or timezone.is_aware(d) else timezone.make_aware(d, dt.UTC)


def merge(config: Any, types: list[dict[str, Any]], shifts: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict:
    from apps.crew import services as crew
    from apps.crew.models import Assignment, Member, Shift, Team
    from apps.venues.models import Room

    event, source = config.event, source_of(config)
    stats = {"teams": 0, "shifts_new": 0, "shifts_updated": 0, "shifts_removed": 0, "signups": 0, "kept": 0}
    rooms = {r.name.lower(): r for r in Room.objects.filter(venue__in=event.venues.all())}
    with transaction.atomic():
        teams: dict[str, Team] = {}
        for t in types:
            ext = str(t["id"])
            team = (Team.objects.filter(event=event, source=source, external_id=ext).first()
                    or Team.objects.filter(event=event, name=str(t.get("name") or ext)[:80], source="").first())
            if team is None:
                team = Team.objects.create(event=event, name=str(t.get("name") or ext)[:80], source=source,
                                           external_id=ext, description=str(t.get("description") or "")[:2000])
                stats["teams"] += 1
            elif not team.source:
                team.source, team.external_id = source, ext
                team.save(update_fields=["source", "external_id"])
            teams[ext] = team
        seen: set[str] = set()
        for t, s in shifts:
            team = teams[str(t["id"])]
            need = next((n for n in s.get("needed_angel_types") or []
                         if str((n.get("angel_type") or {}).get("id")) == str(t["id"])), None)
            start, end = _when(s.get("starts_at") or s.get("start")), _when(s.get("ends_at") or s.get("end"))
            if start is None or end is None or end <= start:
                continue
            ext = f"{s.get('id')}:{t['id']}"
            seen.add(ext)
            where = str((s.get("location") or {}).get("name") or "")
            title = str(s.get("name") or s.get("title") or (s.get("shift_type") or {}).get("name") or team.name)
            values = {"team": team, "title": title[:150], "starts_at": start, "ends_at": end,
                      "location": where[:150], "room": rooms.get(where.lower()),
                      "needed": max(0, int((need or {}).get("needs") or 1)), "notes": str(s.get("description")
                                                                                           or "")[:2000]}
            shift = Shift.objects.filter(event=event, source=source, external_id=ext).first()
            if shift is None:
                shift = Shift.objects.create(event=event, source=source, external_id=ext, **values)
                stats["shifts_new"] += 1
            else:
                dirty = [k for k, v in values.items() if getattr(shift, k) != v]
                if dirty:
                    for k in dirty:
                        setattr(shift, k, values[k])
                    shift.save()
                    stats["shifts_updated"] += 1
            upstream: set[str] = set()
            for e in (need or {}).get("entries") or []:
                u = e.get("user") or {}
                if u.get("id") is None:
                    continue
                uid = str(u["id"])
                upstream.add(uid)
                m = Member.objects.filter(event=event, source=source, external_id=uid).first()
                if m is None:
                    m = Member.objects.create(event=event, source=source, external_id=uid,
                                              name=str(u.get("name") or uid)[:120])
                m.teams.add(team)
                a, created = Assignment.objects.get_or_create(shift=shift, member=m, defaults={"source": source})
                stats["signups"] += int(created)
            # removed upstream: only sign-ups that came from Engelsystem and were not acted on here
            for a in shift.assignments.filter(source=source, status=Assignment.Status.SIGNED_UP).select_related(
                    "member"):
                if a.member.source == source and a.member.external_id not in upstream:
                    a.delete()
        for shift in Shift.objects.filter(event=event, source=source).exclude(external_id__in=seen):
            if shift.assignments.exclude(status=Assignment.Status.SIGNED_UP).exists() or \
                    shift.assignments.exclude(source=source).exists():
                stats["kept"] += 1
                continue
            shift.delete()
            stats["shifts_removed"] += 1
    crew.changed(event)
    return stats


def summary(stats: dict[str, int]) -> str:
    return _("%(n)s new and %(u)s changed shifts, %(r)s removed, %(s)s new sign-ups, %(t)s new teams, %(k)s kept "
             "(local check-ins)") % {"n": stats["shifts_new"], "u": stats["shifts_updated"],
                                     "r": stats["shifts_removed"], "s": stats["signups"], "t": stats["teams"],
                                     "k": stats["kept"]}


def run(config: Any) -> dict[str, int]:
    from apps.extensions import services as ext

    types, shifts = fetch(config)
    stats = merge(config, types, shifts)
    config.last_sync_at = timezone.now()
    config.last_error = ""
    config.save(update_fields=["last_sync_at", "last_error"])
    ext.write_log(config, "info", f"Engelsystem sync: {summary(stats)}")
    return stats


def handle_job(job: Any) -> None:
    from apps.core import modules
    from apps.extensions import services as ext
    from apps.extensions.models import ExtensionConfig

    config = ExtensionConfig.objects.select_related("event").filter(pk=job.payload["config"], enabled=True).first()
    if config is None or config.event_id is None or not config.feature_enabled("shifts"):
        job.result = {"skipped": "gone or disabled"}
        return
    if not modules.is_enabled("crew", config.event):
        job.result = {"skipped": "crew module off"}
        return
    try:
        stats = run(config)
    except SyncError as exc:
        config.last_error = str(exc)[:500]
        config.save(update_fields=["last_error"])
        ext.write_log(config, "error", f"Engelsystem sync failed: {exc}")
        job.result = {"failed": str(exc)[:300]}
        return
    job.result = stats


def queue(config: Any, *, reason: str = "manual") -> Any:
    bucket = int(timezone.now().timestamp() // 30)
    return outbox.enqueue(JOB, {"config": str(config.pk), "reason": reason}, event=config.event,
                          key=f"engelsystem-sync:{config.pk}:{bucket}:{reason}")


def sync_due(now: dt.datetime | None = None) -> int:
    from apps.extensions.models import ExtensionConfig

    now = now or timezone.now()
    n = 0
    for config in ExtensionConfig.objects.filter(extension=KEY, enabled=True, event__isnull=False):
        value = (config.settings or {}).get("interval_minutes")
        minutes = 15 if value is None or value == "" else int(value)
        if minutes <= 0 or not config.feature_enabled("shifts"):
            continue
        if config.last_sync_at is None or config.last_sync_at + dt.timedelta(minutes=minutes) <= now:
            queue(config, reason="periodic")
            n += 1
    return n


def test_connection(config: Any) -> ConnectionResult:
    try:
        info = _get(config, "/info")
        types, shifts = fetch(config)
    except SyncError as exc:
        return ConnectionResult(False, str(exc))
    name = info.get("name") if isinstance(info, dict) else ""
    return ConnectionResult(True, _("%(e)s: %(t)s angel types, %(s)s shifts. Nothing was imported yet: use "
                                    "“Sync now”.") % {"e": name or "Engelsystem", "t": len(types),
                                                       "s": len(shifts)})


def purge(config: Any) -> None:
    from apps.crew.models import Member, Shift, Team

    source = source_of(config)
    Shift.objects.filter(event=config.event, source=source).delete()
    Member.objects.filter(event=config.event, source=source, user__isnull=True).delete()
    Team.objects.filter(event=config.event, source=source, shifts__isnull=True).delete()
