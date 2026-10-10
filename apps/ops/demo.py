# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demo operations for ``evac_seed_demo``: a few incidents in different states, ops log traffic, tasks and an
escalation rule."""
from __future__ import annotations

from typing import Any

from . import services
from .models import EscalationRule, Incident, Task


def seed(event: Any, actor: Any) -> int:
    if Incident.objects.filter(event=event).exists():
        return 0
    from apps.accounts.models import User
    from apps.venues.models import Room, Zone

    rooms = {r.name: r for r in Room.objects.filter(venue__in=event.venues.all())}
    zones = {z.name: z for z in Zone.objects.filter(venue__in=event.venues.all())}
    sam = User.objects.filter(email="security@evac.local").first()
    control = event.roles.filter(key="control-room").first()
    security = event.roles.filter(key="security").first()
    rule = EscalationRule(event=event, name="High and critical: control room", min_severity="high")
    services.save_rule(rule, actor=actor, roles=[r for r in (control,) if r])
    later = EscalationRule(event=event, name="Not acknowledged after 5 minutes: security", min_severity="medium",
                           after_minutes=5)
    services.save_rule(later, actor=actor, roles=[r for r in (security,) if r])
    made = []
    for title, cat, sev, room, zone, where, who, note in [
        ("Person collapsed near the bar", "Medical", "high", "Hall A", None, "Bar, left side", "Bar staff",
         "Conscious, breathing. Medics called."),
        ("Broken glass on the stairs", "Technical", "low", "Foyer", None, "Main stairs", "Cleaning team", ""),
        ("Crowd pressure at entrance north", "Crowd", "medium", None, "Zone North", "Gate N2", "Security 2",
         "Queue backs up onto the street."),
        ("Lost child: Mia, 6, red jacket", "Lost child", "critical", None, "Courtyard", "Info point", "Mother",
         "Last seen at the food trucks 10 minutes ago."),
    ]:
        inc = Incident(event=event, title=title, category=cat, severity=sev, room=rooms.get(room) if room else None,
                       zone=zones.get(zone) if zone else None, location=where, reported_by=who, source="manual")
        services.create_incident(inc, actor=actor, note=note)
        made.append(inc)
    services.set_status(made[0], Incident.Status.IN_PROGRESS, actor=actor, note="Medics on site")
    if sam:
        made[2].assignee = sam
        services.update_incident(made[2], ["assignee"], actor=actor, before={"assignee": None})
    services.set_status(made[1], Incident.Status.RESOLVED, actor=actor, note="Swept up, area dry")
    for sender, to, text, important in [
        ("Security 2", "Control", "Gate N2 queue about 80 m, opening the second lane", False),
        ("Control", "All units", "Lost child: Mia, 6, red jacket. Bring her to the info point.", True),
        ("Medic 1", "Control", "On site at Hall A bar, patient stable", False),
    ]:
        services.add_entry(event, text, actor=actor, sender=sender, recipient=to, important=important)
    Task.objects.create(event=event, title="Check the barrier at gate N2", team="Security", incident=made[2],
                        created_by=actor)
    Task.objects.create(event=event, title="Restock first aid kit at Hall A", team="Medics", created_by=actor)
    return len(made)
