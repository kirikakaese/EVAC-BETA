# SPDX-License-Identifier: AGPL-3.0-or-later
"""The door counter card of the staff page (PWA): links to each area's clicker with its live count."""
from __future__ import annotations

from typing import Any

from apps.events import rbac

from .models import Area


def card(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "crowd.count", request=request):
        return None
    areas = [a for a in Area.objects.filter(event=event).select_related("room", "zone")
             if rbac.has_perm(request.user, event, "crowd.count", obj=a, request=request)]
    return {"areas": areas}
