# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demo program for ``evac_seed_demo``: two days of sessions on three stages around today, with one delay."""
from __future__ import annotations

import datetime as dt
import zoneinfo
from typing import Any

from django.utils import timezone

from . import services
from .models import Session, Speaker, Stage, Track

STAGES = [("Main stage", "Hall A"), ("Stage B", "Hall B"), ("Workshop room", "Workshop 1")]
TRACKS = [("Keynotes", "#15803d"), ("Technology", "#2563eb"), ("Hands-on", "#c2410c")]
# (day, start hh:mm, minutes, stage index, track index, title, speakers)
TALKS = [
    (0, "10:00", 45, 0, 0, "Opening: welcome to the Demo Festival", ["Olivia Orga"]),
    (0, "11:00", 45, 0, 1, "Screens that keep working offline", ["Ada Byron"]),
    (0, "12:00", 30, 0, 1, "Lightning talks", ["Several speakers"]),
    (0, "14:00", 60, 0, 0, "Panel: safety at large events", ["Sam Security", "Carl Control"]),
    (0, "16:00", 45, 0, 1, "From pretalx to the foyer screen", ["Grace Hopper"]),
    (0, "18:00", 60, 0, 0, "Evening keynote", ["Katherine Johnson"]),
    (0, "10:30", 60, 1, 1, "Building layouts in the editor", ["Chris Crew"]),
    (0, "12:00", 45, 1, 1, "Announcements without panic", ["Hana Helpdesk"]),
    (0, "15:00", 60, 1, 1, "Radio, DECT and the control room", ["Linus Signal"]),
    (0, "17:00", 45, 1, 0, "Volunteers' stories", ["Vic Viewer"]),
    (0, "11:00", 90, 2, 2, "Soldering for beginners", ["Margaret Hamilton"]),
    (0, "14:00", 120, 2, 2, "Build a status light", ["Alan Kay"]),
    (1, "10:00", 45, 0, 0, "Day two: good morning", ["Olivia Orga"]),
    (1, "11:00", 60, 0, 1, "Data widgets in practice", ["Ada Byron"]),
    (1, "11:00", 90, 2, 2, "Repair café", ["Margaret Hamilton"]),
]


def seed(event: Any, actor: Any) -> int:
    """Create the demo program once (returns the number of sessions created)."""
    if Session.objects.filter(event=event).exists():
        return 0
    from apps.venues.models import Room

    tz = zoneinfo.ZoneInfo(event.timezone or "UTC")
    rooms = {r.name: r for r in Room.objects.filter(venue__in=event.venues.all())}
    stages = [Stage.objects.get_or_create(event=event, name=name, defaults={"room": rooms.get(room), "order": i})[0]
              for i, (name, room) in enumerate(STAGES)]
    tracks = [Track.objects.get_or_create(event=event, name=n, defaults={"colour": c})[0] for n, c in TRACKS]
    today = timezone.localdate(timezone=tz)
    created = []
    for day, start, minutes, st, tr, title, people in TALKS:
        h, m = (int(x) for x in start.split(":"))
        begin = dt.datetime.combine(today + dt.timedelta(days=day), dt.time(h, m), tz)
        s = Session.objects.create(event=event, title=title, stage=stages[st], track=tracks[tr], starts_at=begin,
                                   ends_at=begin + dt.timedelta(minutes=minutes), kind="talk", language="en")
        s.speakers.set([Speaker.objects.get_or_create(event=event, name=n)[0] for n in people])
        created.append(s)
    services.delay(created[2], 10, actor=actor, note="Starts 10 min late")
    services.move(created[8], stages[0], actor=actor)
    return len(created)
