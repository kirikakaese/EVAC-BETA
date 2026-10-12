# SPDX-License-Identifier: AGPL-3.0-or-later
"""Heartbeat pages: the event's health and check-in page, the check-in action and the instance-wide view."""
from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import alerts, modules
from apps.events import rbac
from apps.portal.shortcuts import event_view, safe_next, superuser_view

from . import checkin, services

MODULE = "heartbeat"


@event_view("heartbeat.view", module=MODULE)
def index(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    from apps.nodes import guard

    cfg = services.settings_of(event)
    return render(request, "heartbeat/index.html", {
        "event": event, "ov": services.overview(event), "now": timezone.now(), "cfg": cfg,
        "checkin": checkin.status(event), "can_checkin": checkin.may_check_in(request.user, event, request),
        "history": checkin.history(event), "channels": alerts.channels(event),
        "can_manage": rbac.has_any(request.user, event, "heartbeat.manage", request=request),
        "remote": guard.remote(event),
        **_role_names(event, cfg),
    })


def _role_names(event: Any, cfg: dict[str, Any]) -> dict[str, list[str]]:
    names = {r.key: r.name for r in event.roles.all()}
    return {f"{k}_names": [names.get(str(x), str(x)) for x in cfg.get(k) or []]
            for k in ("notify_roles", "checkin_roles", "checkin_escalation")}


@require_POST
@event_view(None, module=MODULE)
def check_in(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    source = request.POST.get("source", "page")
    try:
        checkin.check_in(event, request.user, request=request,
                         source=source if source in ("page", "dashboard", "staff") else "page")
    except ValidationError as err:
        for m in err.messages:
            messages.error(request, m)
    else:
        messages.success(request, _("Checked in. Thank you."))
    return redirect(safe_next(request, f"/e/{slug}/heartbeat/"))


@superuser_view
def instance(request: HttpRequest) -> HttpResponse:
    if not modules.is_enabled(MODULE):
        raise Http404("Module disabled")
    return render(request, "heartbeat/instance.html", {"ov": services.overview(None), "now": timezone.now()})
