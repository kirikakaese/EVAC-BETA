# SPDX-License-Identifier: AGPL-3.0-or-later
"""The evacuation card of the staff page (PWA): current state, requests waiting, the panic page."""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.events import rbac

from . import acks, machine, services, triggers
from .models import StaffAck


def card(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "evacuation.view", request=request):
        return None
    cfg = services.config(event)
    ev, _zones = services.statuses(event)
    now = machine.current(ev, timezone.now())
    return {"state": now.state.value, "label": cfg.labels[now.state.value], "drill": now.drill,
            "drill_text": cfg.drill_text, "pending": len(triggers.pending(event)),
            "alarm": acks.alarm_since(event) is not None, "kinds": StaffAck.KINDS,
            "zones": list(services.zones_of(event)) if cfg.model is machine.Model.ZONES else [],
            "can_raise": any(rbac.has_any(request.user, event, p, request=request)
                             for p in (services.PERM_TRIGGER, services.PERM_DRILL))}
