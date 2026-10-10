# SPDX-License-Identifier: AGPL-3.0-or-later
"""The evacuation panel of the control room dashboard (ADR-0039): the event's state and every zone in alarm."""
from __future__ import annotations

from typing import Any

from apps.events import rbac

from . import services
from .models import EvacState


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "evacuation.view", request=request):
        return None
    cfg = services.config(event)
    ev, _zones = services.statuses(event)
    zones = [{"name": r.zone.name, "status": r.status, "label": cfg.labels.get(r.status.state, r.status.state)}
             for r in EvacState.objects.filter(event=event, zone__isnull=False).select_related("zone")
             if r.status.alarm or r.status.state == "all_clear"]
    return {"status": ev, "label": cfg.labels.get(ev.state, ev.state), "zones": zones,
            "alarm": ev.alarm or any(z["status"].alarm for z in zones)}
