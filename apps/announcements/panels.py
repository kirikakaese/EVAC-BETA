# SPDX-License-Identifier: AGPL-3.0-or-later
"""The announcements panel of the control room dashboard (ADR-0039): on air, waiting for approval, recent."""
from __future__ import annotations

from typing import Any

from . import services
from .models import Announcement


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    if not services.rbac_any(request.user, event, "announcements.view", request):
        return None
    qs = Announcement.objects.filter(event=event).select_related("level")
    return {"live": list(qs.filter(status=Announcement.Status.LIVE).order_by("-published_at")[:5]),
            "pending": qs.filter(status=Announcement.Status.PENDING).count(),
            "recent": list(qs.filter(published_at__isnull=False).exclude(status=Announcement.Status.LIVE)
                           .order_by("-published_at")[:4])}
