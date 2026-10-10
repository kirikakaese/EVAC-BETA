# SPDX-License-Identifier: AGPL-3.0-or-later
"""The operations card of the staff page (PWA): open incidents, “I'm on it”, a quick report and an ops log line.
The forms work offline: the staff app queues them with a client id and the server ignores a replay."""
from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import services
from .forms import QuickIncidentForm
from .models import Incident


def card(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "ops.view", request=request):
        return None
    can_report = rbac.has_any(request.user, event, "ops.report", request=request)
    qs = Incident.objects.filter(event=event, status__in=Incident.OPEN).select_related("zone", "room")
    mine = list(qs.filter(assignee=request.user)[:5])
    fresh = list(qs.filter(status=Incident.Status.NEW).exclude(assignee=request.user).order_by("-created_at")[:5])
    return {"mine": mine, "fresh": sorted(fresh, key=lambda i: -i.rank), "can_report": can_report,
            "categories": services.categories(event), "severities": Incident.Severity.choices,
            "open": qs.count()}


def _back(request: Any, slug: str) -> Any:
    nxt = request.POST.get("next") or ""
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else f"/e/{slug}/staff/")


@require_POST
@event_view("ops.report", module="ops")
def report(request, slug, *, event):
    form = QuickIncidentForm(request.POST)
    client_id = (request.POST.get("client_id") or "")[:64]
    if client_id and Incident.objects.filter(event=event, source="staff", external_id=client_id).exists():
        return _back(request, slug)  # a replay from the offline queue
    if not form.is_valid():
        messages.error(request, _("Describe what happened."))
        return _back(request, slug)
    d = form.cleaned_data
    cats = services.categories(event)
    inc = Incident(event=event, title=d["title"], severity=d["severity"], location=d["location"],
                   category=d["category"] if d["category"] in cats else (cats[-1] if cats else "Other"),
                   source="staff", external_id=client_id, reported_by=str(request.user)[:120])
    try:
        services.create_incident(inc, actor=request.user, request=request)
    except ValidationError as err:
        for m in err.messages:
            messages.error(request, m)
    else:
        messages.success(request, _("Incident #%(n)s reported; the control room sees it.") % {"n": inc.number})
    return _back(request, slug)


@require_POST
@event_view("ops.report", module="ops")
def log_entry(request, slug, *, event):
    try:
        services.add_entry(event, request.POST.get("text", ""), actor=request.user,
                           sender=request.POST.get("sender") or str(request.user), recipient=request.POST.get(
                               "recipient", ""), important=bool(request.POST.get("important")),
                           client_id=request.POST.get("client_id", ""),
                           at=parse_datetime(request.POST.get("written_at") or "") or None, request=request)
    except ValidationError as err:
        for m in err.messages:
            messages.error(request, m)
    else:
        messages.success(request, _("Written to the ops log."))
    return _back(request, slug)


@require_POST
@event_view("ops.view", module="ops")
def acknowledge(request, slug, pk, *, event):
    inc = Incident.objects.filter(event=event, pk=pk).first()
    if inc is None:
        return _back(request, slug)
    if not rbac.has_perm(request.user, event, "ops.report", obj=inc, request=request):
        raise PermissionDenied("ops.report")
    if inc.status == Incident.Status.NEW:  # a replay after someone else acknowledged is fine
        services.set_status(inc, Incident.Status.ACKNOWLEDGED, actor=request.user, request=request,
                            note=_("%(u)s is on it") % {"u": request.user})
        if inc.assignee_id is None:
            before = {"assignee": None}
            inc.assignee = request.user
            services.update_incident(inc, ["assignee"], actor=request.user, request=request, before=before)
    return _back(request, slug)
