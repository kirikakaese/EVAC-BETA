# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpdesk in the control room, on the staff page and on screens (FAQ, found items, the queue)."""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.events import rbac

from . import services
from .models import FaqEntry, LostFound, Ticket


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "helpdesk.view", request=request):
        return None
    tickets = services.open_tickets(event)
    return {"new": tickets.filter(status=Ticket.Status.NEW).count(), "open": tickets.count(),
            "latest": list(tickets[:6]),
            "lost": LostFound.objects.filter(event=event, kind="lost", status="open").count(),
            "found": LostFound.objects.filter(event=event, kind="found", status="open").count()}


def staff_card(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "helpdesk.view", request=request):
        return None
    tickets = services.open_tickets(event)
    return {"mine": list(tickets.filter(assignee=request.user)[:10]),
            "new": tickets.filter(status=Ticket.Status.NEW).count(),
            "can_manage": rbac.has_any(request.user, event, "helpdesk.manage", request=request)}


def faq_source(event: Any, **_kw: Any) -> dict[str, Any]:
    items = [{"title": e.question, "subtitle": e.answer, "label": e.topic}
             for e in FaqEntry.objects.filter(event=event, on_screens=True)[:50]]
    return {"items": items}


def found_source(event: Any, **_kw: Any) -> dict[str, Any]:
    """Found items for screens: what, category, colour and the day; never details or contacts."""
    tz = services._tz(event)
    items = []
    for o in services.public_found(event, limit=30):
        at = timezone.localtime(o.when or o.created_at, tz)
        items.append({"title": o.what, "subtitle": o.get_category_display(), "label": o.colour,
                      "time": at.isoformat(), "value": o.reference})
    return {"items": items, "count": len(items)}


def queue_source(event: Any, **_kw: Any) -> dict[str, Any]:
    tickets = services.open_tickets(event)
    return {"open": tickets.count(), "new": tickets.filter(status=Ticket.Status.NEW).count()}
