# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demo helpdesk for ``evac_seed_demo``: FAQ entries, lost reports and found items (one pair matches), requests."""
from __future__ import annotations

from typing import Any

from . import services
from .models import FaqEntry, LostFound, Ticket


def seed(event: Any, actor: Any) -> int:
    if FaqEntry.objects.filter(event=event).exists():
        return 0
    for topic, q, a, screens in [
        ("Venue", "Where is the cloakroom?", "In the foyer, left of the main entrance. Open until 1 am.", True),
        ("Venue", "Is there step-free access?", "Yes: all halls are step-free; the workshops upstairs have a lift. "
                                                "Ask at the helpdesk for the accessible route.", True),
        ("Tickets", "Can I leave and come back?", "Yes, keep your wristband on.", True),
        ("Lost & found", "I lost something. What now?", "Report it on this page or at the helpdesk in the foyer. "
                                                        "We check every found item against the reports.", False),
    ]:
        FaqEntry.objects.create(event=event, topic=topic, question=q, answer=a, on_screens=screens)
    for kind, what, cat, colour, where, desc, name, contact, storage in [
        ("lost", "Black backpack", "bag", "black", "Hall A", "Laptop and a blue water bottle inside", "Jonas",
         "0170 555 0199", ""),
        ("found", "Backpack", "bag", "black", "Hall A, row 12", "Laptop inside", "Cleaning team", "", "Helpdesk box 1"),
        ("found", "Car keys with a red tag", "keys", "red", "Beer garden", "VW key", "Bar staff", "",
         "Helpdesk key box"),
        ("found", "Rain jacket", "clothing", "green", "Foyer", "Size M", "", "", "Helpdesk rail"),
        ("lost", "Glasses", "glasses", "brown", "Workshop 1", "Brown frame in a grey case", "Ana", "ana@example.org",
         ""),
    ]:
        services.save_item(LostFound(event=event, kind=kind, what=what, category=cat, colour=colour, where=where,
                                     description=desc, name=name, contact=contact, storage=storage), actor=actor)
    for cat, subject, body, name in [
        ("accessibility", "Wheelchair space in Hall B", "Is there a wheelchair space left for the 8 pm concert?",
         "Kim"),
        ("question", "Lockers", "Are there lockers for a big bag?", ""),
        ("problem", "Toilet out of order", "The second toilet in the foyer is blocked.", "Sam"),
    ]:
        services.submit(Ticket(event=event, category=cat, subject=subject, body=body, name=name, source="public"),
                        actor=None)
    return 1
