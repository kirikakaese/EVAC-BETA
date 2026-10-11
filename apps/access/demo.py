# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demo access data for ``evac_seed_demo``: ticket types, zones (the entrance feeds the occupancy area "Festival
site"), 40 attendees with readable codes (DEMO-0001 …) and a few scans."""
from __future__ import annotations

from typing import Any

from . import services
from .models import AccessZone, Attendee, TicketType

FIRST = ["Ada", "Grace", "Alan", "Margaret", "Linus", "Barbara", "Dennis", "Frances", "Ken", "Radia", "Tim",
         "Hedy", "Donald", "Katherine", "Edsger", "Annie", "Niklaus", "Shafi", "Guido", "Sophie"]
LAST = ["Lovelace", "Hopper", "Turing", "Hamilton", "Torvalds", "Liskov", "Ritchie", "Allen", "Thompson",
        "Perlman", "Berners-Lee", "Lamarr", "Knuth", "Johnson", "Dijkstra", "Easley", "Wirth", "Goldwasser",
        "van Rossum", "Wilson"]


def seed(event: Any, actor: Any) -> int:
    if TicketType.objects.filter(event=event).exists():
        return 0
    from django.apps import apps

    from apps.venues.models import Room

    foyer = Room.objects.filter(venue__in=event.venues.all(), name="Foyer").first()
    area_id = None
    if apps.is_installed("apps.crowd"):
        from apps.crowd.models import Area

        site = Area.objects.filter(event=event, name="Festival site").first() or Area.objects.create(
            event=event, name="Festival site", capacity=2500, order=0)
        area_id = site.pk
    entrance = AccessZone.objects.create(event=event, name="Main entrance", open_to_all=True, checkin=True,
                                         room=foyer, area_id=area_id, order=1)
    backstage = AccessZone.objects.create(event=event, name="Backstage", reentry=True, order=2)
    crew_area = AccessZone.objects.create(event=event, name="Crew area", order=3)
    types = {}
    for i, (name, colour, zones) in enumerate([("Day ticket", "#2563eb", []), ("Weekend", "#7c3aed", []),
                                                ("Crew", "#16a34a", [backstage, crew_area]),
                                                ("Artist", "#db2777", [backstage])]):
        t = TicketType.objects.create(event=event, name=name, colour=colour, order=i)
        t.zones.set(zones)
        types[name] = t
    kinds = ["Day ticket"] * 14 + ["Weekend"] * 16 + ["Crew"] * 6 + ["Artist"] * 4
    made = []
    for i, kind in enumerate(kinds):
        a = Attendee(event=event, name=f"{FIRST[i % 20]} {LAST[(i * 7) % 20]}", ticket_type=types[kind],
                     code=f"DEMO-{i + 1:04d}", company="Demo Records" if kind == "Artist" else "",
                     email=f"guest{i + 1}@example.org", source="demo")
        made.append(services.save_attendee(a, actor=actor))
    Attendee.objects.filter(pk=made[-5].pk).update(status=Attendee.Status.CANCELLED)
    for a in made[:8]:
        services.scan(entrance, a.code, actor=actor, device="Gate 1")
    services.scan(entrance, "FORGED-123", actor=actor, device="Gate 1")
    return len(made)
