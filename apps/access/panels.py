# SPDX-License-Identifier: AGPL-3.0-or-later
"""Access in the control room, on the staff page, on screens and as a scope kind."""
from __future__ import annotations

from typing import Any

from apps.events import rbac

from . import services
from .models import AccessZone


def zone_choices(event: Any) -> list[tuple[str, str]]:
    return [(str(z.pk), z.name) for z in AccessZone.objects.filter(event=event)]


def scan_zones(request: Any, event: Any) -> list[AccessZone]:
    return [z for z in AccessZone.objects.filter(event=event)
            if rbac.has_perm(request.user, event, "access.scan", obj=z, request=request)]


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "access.view", request=request):
        return None
    return services.stats(event)


def staff_card(request: Any, event: Any) -> dict[str, Any] | None:
    zones = scan_zones(request, event)
    return {"zones": zones} if zones else None


def zones_source(event: Any, **_kw: Any) -> dict[str, Any]:
    s = services.stats(event)
    return {"items": [{"title": z.name, "value": z.n} for z in s["zones"]], "checked_in": s["checked_in"],
            "total": s["total"]}
