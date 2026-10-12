# SPDX-License-Identifier: AGPL-3.0-or-later
"""The heartbeat panel of the control room dashboard and the check-in card of the staff app."""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.events import rbac

from . import checkin, services


def _checkin(request: Any, event: Any) -> dict[str, Any] | None:
    st = checkin.status(event)
    if not st.enabled:
        return None
    return {"status": st, "can": checkin.may_check_in(request.user, event, request), "now": timezone.now()}


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    can_view = rbac.has_any(request.user, event, "heartbeat.view", request=request)
    ci = _checkin(request, event)
    if not can_view and not (ci and ci["can"]):
        return None
    # the panel refreshes itself (htmx): after a check-in, go back to the dashboard, not to the panel fragment
    ctx: dict[str, Any] = {"checkin": ci, "can_view": can_view,
                           "next": request.headers.get("HX-Current-URL") or request.get_full_path()}
    if can_view:
        ov = services.overview(event)
        ctx.update(counts=ov["counts"], problems=ov["problems"][:8], worst=ov["worst"],
                   total=len(ov["observations"]))
    return ctx


def staff_card(request: Any, event: Any) -> dict[str, Any] | None:
    ci = _checkin(request, event)
    if ci is None or not ci["can"] or not ci["status"].active:
        return None
    return {"checkin": ci}
