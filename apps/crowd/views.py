# SPDX-License-Identifier: AGPL-3.0-or-later
"""Occupancy pages: the overview, an area with its history, the door counter (staff app) and its batch endpoint."""
from __future__ import annotations

import json
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST, require_safe

from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import services
from .forms import AreaForm, CorrectionForm
from .models import Area, CountEvent

MODULE = "crowd"


def _fail(request: Any, err: ValidationError) -> None:
    for m in err.messages:
        messages.error(request, m)


def _area(event: Any, pk: Any) -> Area:
    return get_object_or_404(Area.objects.select_related("room", "zone", "alternative"), event=event, pk=pk)


@event_view("crowd.view", module=MODULE)
def index(request, slug, *, event):
    can_manage = rbac.has_any(request.user, event, "crowd.manage", request=request)
    form = AreaForm(request.POST or None, instance=Area(event=event), event=event) if can_manage else None
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied("crowd.manage")
        if request.POST.get("what") == "reset":
            n = services.reset_all(event, actor=request.user, request=request)
            messages.success(request, _("%(n)s areas set to 0.") % {"n": n})
            return redirect("crowd:index", slug)
        if form.is_valid():
            area = form.save(commit=False)
            try:
                services.save_area(area, actor=request.user, request=request, m2m={
                    "screen_groups": form.cleaned_data["screen_groups"],
                    "notify_roles": form.cleaned_data["notify_roles"]})
            except ValidationError as err:
                _fail(request, err)
            else:
                messages.success(request, _("Area added."))
                return redirect("crowd:index", slug)
    areas = list(Area.objects.filter(event=event).select_related("room", "zone", "alternative"))
    for a in areas:
        a.bar = min(100, round((a.percent or 0) / 5) * 5)
    return render(request, "crowd/index.html", {
        "event": event, "areas": areas, "form": form, "can_manage": can_manage,
        "can_count": rbac.has_any(request.user, event, "crowd.count", request=request),
        "total": sum(a.value for a in areas)})


@event_view("crowd.view", module=MODULE)
def area(request, slug, pk, *, event):
    a = _area(event, pk)
    can_manage = rbac.has_perm(request.user, event, "crowd.manage", obj=a, request=request)
    form = AreaForm(request.POST or None, instance=a, event=event) if can_manage else None
    correction = CorrectionForm(request.POST if request.POST.get("what") == "correct" else None)
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied("crowd.manage")
        if request.POST.get("what") == "correct":
            if correction.is_valid():
                services.set_value(a, correction.cleaned_data["value"], source=CountEvent.Source.CORRECTION,
                                   actor=request.user, request=request, device=_("correction"))
                messages.success(request, _("Count set."))
                return redirect("crowd:area", slug, a.pk)
        elif request.POST.get("what") == "delete":
            services.delete_area(a, actor=request.user, request=request)
            messages.success(request, _("Area deleted."))
            return redirect("crowd:index", slug)
        elif form is not None and form.is_valid():
            try:
                services.save_area(form.save(commit=False), actor=request.user, request=request, m2m={
                    "screen_groups": form.cleaned_data["screen_groups"],
                    "notify_roles": form.cleaned_data["notify_roles"]})
            except ValidationError as err:
                _fail(request, err)
            else:
                messages.success(request, _("Saved."))
                return redirect("crowd:area", slug, a.pk)
    hours = 12 if request.GET.get("hours") not in ("2", "6", "24", "48") else int(request.GET["hours"])
    samples = services.history(a, hours=hours)
    return render(request, "crowd/area.html", {
        "event": event, "area": a, "form": form, "correction": correction, "can_manage": can_manage,
        "chart": services.chart(a, samples, hours=hours), "hours": hours,
        "recent": a.counts.select_related("user")[:30], "suggestion": services.suggestion(a),
        "can_count": rbac.has_perm(request.user, event, "crowd.count", obj=a, request=request)})


# ------------------------------------------------------------------ door counter
@event_view("crowd.count", module=MODULE)
def counter(request, slug, pk, *, event):
    a = _area(event, pk)
    if not rbac.has_perm(request.user, event, "crowd.count", obj=a, request=request):
        raise PermissionDenied("crowd.count")
    return render(request, "crowd/counter.html", {"event": event, "area": a})


@require_POST
@event_view("crowd.count", module=MODULE)
def counts(request, slug, *, event):
    """The counter's batch: ``{"counts": [{"area", "delta", "id", "at", "device"}]}`` (queued clicks, oldest first).
    Answers the current state of the areas involved. Replays of the same ``id`` are ignored."""
    try:
        body = json.loads(request.body or b"{}")
        items = body.get("counts") if isinstance(body, dict) else None
        if not isinstance(items, list) or len(items) > 500:
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "send {\"counts\": [...]}"}, status=400)
    touched: dict[str, Area] = {}
    refused = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        a = touched.get(str(it.get("area"))) or Area.objects.filter(event=event, pk=_uuid(it.get("area"))).first()
        if a is None or not rbac.has_perm(request.user, event, "crowd.count", obj=a, request=request):
            refused += 1
            continue
        delta = it.get("delta")
        if isinstance(delta, bool) or not isinstance(delta, int) or abs(delta) > 100:
            refused += 1
            continue
        a = services.count(a, delta, source=CountEvent.Source.CLICKER, device=str(it.get("device") or "")[:80],
                           client_id=str(it.get("id") or "")[:64], at=parse_datetime(str(it.get("at") or "")))
        touched[str(a.pk)] = a
    return JsonResponse({"areas": {k: _state(a) for k, a in touched.items()}, "refused": refused})


def _uuid(value: Any) -> Any:
    import uuid

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _state(a: Area) -> dict[str, Any]:
    return {"value": a.value, "capacity": a.capacity, "percent": a.percent, "state": a.state,
            "label": a.get_state_display()}


@require_safe
@event_view("crowd.count", module=MODULE)
def state(request, slug, pk, *, event):
    """The counter polls this (other doors count too)."""
    return JsonResponse(_state(_area(event, pk)))
