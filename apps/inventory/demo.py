# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demo inventory for ``evac_seed_demo``: radios, keys, a cargo bike and tools; some lent out, one overdue."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from . import services
from .models import Category, Item, Loan


def seed(event: Any, actor: Any) -> int:
    if Item.objects.filter(event=event).exists():
        return 0
    from apps.venues.models import Room

    store = Room.objects.filter(venue__in=event.venues.all(), name="Foyer").first()
    cats = {n: Category.objects.create(event=event, name=n, loan_hours=h)
            for n, h in [("Radios", 10), ("Keys", 4), ("Vehicles", 2), ("Tools", 0)]}
    made: list[Item] = []
    for name, cat, n, where in [("Radio TH-1", "Radios", 8, "Charging rack"), ("Key Hall B", "Keys", 2, "Key box"),
                                ("Cargo bike", "Vehicles", 1, "Loading dock"), ("Cordless drill", "Tools", 2,
                                                                                  "Tool cage")]:
        made += services.save_item(Item(event=event, name=name, category=cats[cat], room=store, location=where),
                                   actor=actor, copies=n)
    services.lend(made[0], borrower="Chris Crew", contact="DECT 2101", actor=actor,
                  due_at=timezone.now() + dt.timedelta(hours=6))
    services.lend(made[1], borrower="Sam Security", contact="DECT 2201", actor=actor,
                  due_at=timezone.now() + dt.timedelta(hours=8))
    loan = services.lend(made[8], borrower="Olivia Orga", actor=actor, due_at=timezone.now() + dt.timedelta(hours=1))
    Loan.objects.filter(pk=loan.pk).update(lent_at=timezone.now() - dt.timedelta(hours=5),
                                           due_at=timezone.now() - dt.timedelta(hours=1))
    return len(made)
