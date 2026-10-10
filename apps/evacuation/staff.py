# SPDX-License-Identifier: AGPL-3.0-or-later
"""The evacuation card of the staff page (PWA): current state, requests waiting, the panic page."""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.events import rbac

from . import machine, services, triggers


def card(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "evacuation.view", request=request):
        return None
    cfg = services.config(event)
    ev, _zones = services.statuses(event)
    now = machine.current(ev, timezone.now())
    return {"state": now.state.value, "label": cfg.labels[now.state.value], "drill": now.drill,
            "drill_text": cfg.drill_text, "pending": len(triggers.pending(event)),
            "can_raise": any(rbac.has_any(request.user, event, p, request=request)
                             for p in (services.PERM_TRIGGER, services.PERM_DRILL))}
