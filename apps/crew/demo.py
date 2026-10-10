# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demo crew for ``evac_seed_demo``: teams with leads, skills, crew members and shifts around now, some still
short of people (they show on the shift board and the "needed now" screen widget)."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from . import services
from .models import Member, Shift, Skill, Team


def seed(event: Any, actor: Any) -> int:
    if Team.objects.filter(event=event).exists():
        return 0
    from apps.accounts.models import User
    from apps.venues.models import Room

    rooms = {r.name: r for r in Room.objects.filter(venue__in=event.venues.all())}
    chris = User.objects.filter(email="crew@evac.local").first()
    olivia = User.objects.filter(email="orga@evac.local").first()
    first_aid = Skill.objects.create(event=event, name="First aid")
    forklift = Skill.objects.create(event=event, name="Forklift")
    teams = {}
    for name, colour, point, leads in [("Entrance", "#2563eb", "Gate N1", [olivia]),
                                       ("Bar", "#ca8a04", "Bar storage", []),
                                       ("Build-up", "#16a34a", "Loading dock", [olivia])]:
        teams[name] = services.save_team(Team(event=event, name=name, colour=colour, meeting_point=point),
                                         actor=actor, leads=[u for u in leads if u])
    people = []
    for name, contact, team_names, skills, user in [
        ("Chris Crew", "DECT 2101", ["Entrance", "Bar"], [first_aid], chris), ("Ada Lovelace", "DECT 2102",
                                                                                ["Entrance"], [], None),
        ("Grace Hopper", "0170 555 0103", ["Bar"], [], None), ("Linus Field", "DECT 2104", ["Build-up"],
                                                                [forklift], None),
        ("Margaret Hamilton", "DECT 2105", ["Entrance", "Build-up"], [first_aid], None)]:
        m = Member(event=event, name=name, contact=contact, user=user, arrived=True)
        people.append(services.save_member(m, actor=actor, teams=[teams[t] for t in team_names], skills=skills))
    now = timezone.now().replace(minute=0, second=0, microsecond=0)
    # Chris (crew@evac.local) is free until the beer garden: in the demo he scans the wristband QR code and joins
    shifts = [("Entrance", "Ticket check gate N1", "Foyer", -1, 3, 4, [1, 4], []),
              ("Entrance", "Wristbands", "Foyer", 1, 2, 2, [], []),
              ("Bar", "Bar Hall A", "Hall A", 0, 4, 3, [2], []),
              ("Bar", "Bar beer garden", "Beer garden", 5, 4, 2, [0], []),
              ("Build-up", "Stage build Hall B", "Hall B", 1, 3, 3, [3], [forklift])]
    for team, title, room, start, hours, needed, who, skills in shifts:
        s = services.save_shift(Shift(event=event, team=teams[team], title=title, room=rooms.get(room),
                                      starts_at=now + dt.timedelta(hours=start),
                                      ends_at=now + dt.timedelta(hours=start + hours), needed=needed),
                                actor=actor, skills=skills)
        for i in who:
            services.sign_up(s, people[i], actor=actor, force=True)
    return len(shifts)
