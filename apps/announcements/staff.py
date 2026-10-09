# SPDX-License-Identifier: AGPL-3.0-or-later
"""The announcements card of the staff page (PWA): on air now, approvals, quick send."""
from __future__ import annotations

from typing import Any

from . import services
from .models import Announcement, Template


def card(request, event) -> dict[str, Any] | None:
    if not services.rbac_any(request.user, event, "announcements.view", request):
        return None
    services.ensure_defaults(event)
    qs = Announcement.objects.filter(event=event).select_related("level", "created_by")
    pending = [a for a in qs.filter(status=Announcement.Status.PENDING).exclude(created_by=request.user)
               .prefetch_related("venues", "zones", "rooms", "screen_groups", "screens")
               if services.may_target(request.user, a, "announcements.approve", request)]
    can_compose = any(services.rbac_any(request.user, event, p, request)
                      for p in ("announcements.draft", "announcements.publish", "announcements.emergency"))
    return {
        "live": list(qs.filter(status=Announcement.Status.LIVE).order_by("-published_at")[:5]),
        "pending": pending,
        "mine_pending": qs.filter(status=Announcement.Status.PENDING, created_by=request.user).count(),
        "templates": list(Template.objects.filter(event=event).select_related("level")[:8]) if can_compose else [],
        "can_compose": can_compose,
    }
