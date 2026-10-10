# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crew for the control room, as screen data sources, as a scope kind and as an announcement audience."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from apps.events import rbac

from . import services
from .models import Member, Team


def team_choices(event: Any) -> list[tuple[str, str]]:
    return [(str(t.pk), t.name) for t in Team.objects.filter(event=event)]


def team_members(event: Any, ids: set[str]) -> Any:
    """Announcement audience "Team": the accounts of the teams' members and leads (crew calls)."""
    users = {m.user for m in Member.objects.filter(event=event, teams__pk__in=ids, user__isnull=False)
             .select_related("user")}
    for t in Team.objects.filter(event=event, pk__in=ids).prefetch_related("leads"):
        users |= set(t.leads.all())
    return users


def needed_now_source(event: Any, **_kw: Any) -> dict[str, Any]:
    items = services.needed_now(event)
    return {"items": items, "missing": sum(i["missing"] for i in items)}


def board_source(event: Any, **_kw: Any) -> dict[str, Any]:
    now = timezone.now()
    tz = services._tz(event)
    items = []
    # a rolling day rather than the calendar day: night shifts of a festival stay on the board after midnight
    for s in services.window(event, now - dt.timedelta(hours=1), now + dt.timedelta(hours=24)):
        items.append({"team": s.team.name, "title": s.title, "place": s.place,
                      "time": f"{s.starts_at.astimezone(tz):%H:%M}–{s.ends_at.astimezone(tz):%H:%M}",
                      "filled": f"{s.filled} / {s.needed}", "missing": max(0, s.needed - s.filled),
                      "present": s.present, "now": s.starts_at <= now})
    return {"items": items}


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "crew.view", request=request):
        return None
    items = services.needed_now(event)
    return {"items": items[:10], "missing": sum(i["missing"] for i in items)}
