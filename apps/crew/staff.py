# SPDX-License-Identifier: AGPL-3.0-or-later
"""The crew card of the staff page (PWA): my next shifts with check-in/out, and shifts that need people now."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from apps.events import rbac

from . import services
from .models import Assignment


def card(request: Any, event: Any) -> dict[str, Any] | None:
    if not (rbac.has_any(request.user, event, "crew.self", request=request)
            or rbac.has_any(request.user, event, "crew.view", request=request)):
        return None
    member = services.member_for(request.user, event)
    now = timezone.now()
    mine = []
    if member is not None:
        mine = list(Assignment.objects.filter(member=member, status__in=Assignment.ACTIVE,
                                              shift__ends_at__gt=now - dt.timedelta(hours=1))
                    .select_related("shift__team", "shift__room").order_by("shift__starts_at")[:5])
    can_self = rbac.has_any(request.user, event, "crew.self", request=request)
    needed = services.needed_now(event, now)[:5] if can_self else []
    signed = {str(a.shift_id) for a in mine}
    return {"member": member, "mine": mine, "needed": [n for n in needed if n["id"] not in signed],
            "can_self": can_self, "now": now}
