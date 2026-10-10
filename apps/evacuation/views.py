# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evacuation control page (ADR-0029). Triggers, policies and the PWA panic page follow in roadmap 3.5."""
from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import machine, services
from .forms import EVENT, ChangeForm
from .machine import State
from .models import EvacState, StateChange

MODULE = "evacuation"


def _rows(event: Any, labels: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    now = timezone.now()
    states = {str(r.zone_id) if r.zone_id else EVENT: r for r in EvacState.objects.filter(event=event)
              .select_related("changed_by")}
    ev_row = states.get(EVENT)
    ev = machine.current(ev_row.status, now) if ev_row else machine.NORMAL

    def info(status: machine.Status, row: EvacState | None) -> dict[str, Any]:
        return {"state": status.state.value, "label": labels[status.state.value], "drill": status.drill,
                "since": status.since, "clear_until": status.clear_until, "row": row,
                "alarm": status.alarm}

    zones = []
    for z in services.zones_of(event):
        row = states.get(str(z.pk))
        own = machine.current(row.status, now) if row else machine.NORMAL
        zones.append({"zone": z, "own": info(own, row), "shown": info(machine.effective([ev, own], now), None)})
    return info(ev, ev_row), zones


def _form(request: HttpRequest, event: Any, cfg: services.Config, zones: list[dict[str, Any]],
          data: Any = None) -> ChangeForm:
    alarm_zones = [z["zone"] for z in zones if z["own"]["alarm"]]
    can_drill = rbac.has_any(request.user, event, services.PERM_DRILL, request=request)
    return ChangeForm(data, zones=[z["zone"] for z in zones], labels=cfg.labels, enabled=cfg.enabled,
                      alarm_zones=alarm_zones, can_drill=can_drill)


def _can_change(request: HttpRequest, event: Any) -> bool:
    return any(rbac.has_any(request.user, event, p, request=request)
               for p in (services.PERM_TRIGGER, services.PERM_CLEAR, services.PERM_DRILL))


@event_view("evacuation.view", module=MODULE)
def index(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    return _page(request, event)


def _page(request: HttpRequest, event: Any, form: ChangeForm | None = None) -> HttpResponse:
    cfg = services.config(event)
    ev, zones = _rows(event, cfg.labels)
    can_change = _can_change(request, event)
    return render(request, "evacuation/index.html", {
        "event": event, "ev": ev, "zones": zones, "cfg": cfg, "can_change": can_change,
        "form": form or (_form(request, event, cfg, zones) if can_change else None),
        "history": StateChange.objects.filter(event=event).select_related("actor")[:15],
        "labels": cfg.labels,
    }, status=400 if form is not None else 200)


@require_POST
@event_view("evacuation.view", module=MODULE)
def change(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    if not _can_change(request, event):
        raise PermissionDenied
    cfg = services.config(event)
    _ev, zones = _rows(event, cfg.labels)
    form = _form(request, event, cfg, zones, request.POST)
    if not form.is_valid():
        return _page(request, event, form)
    scope = form.cleaned_data["scope"]
    zone = None if scope == EVENT else next(z["zone"] for z in zones if str(z["zone"].pk) == scope)
    try:
        done = services.change(event, form.cleaned_data["state"], zone=zone,
                               drill=bool(form.cleaned_data.get("drill")), actor=request.user, request=request,
                               reason=form.cleaned_data["reason"],
                               clear_zones=form.cleaned_data.get("clear_zones") if "clear_zones" in form.fields
                               else None)
    except machine.Refused as err:
        form.add_error(None, err.message)
        return _page(request, event, form)
    except PermissionDenied:
        form.add_error(None, _("You may not make this change here."))
        return _page(request, event, form)
    first = done[0]
    messages.success(request, _("%(where)s: %(state)s%(drill)s.") % {
        "where": first.zone_name or _("Whole event"), "state": cfg.labels[first.to_state],
        "drill": f" ({cfg.drill_text})" if first.drill and first.to_state != State.NORMAL else ""})
    return redirect("evacuation:index", event.slug)


@require_POST
@event_view("evacuation.view", module=MODULE)
def end_all_clear(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    zone_id = request.POST.get("zone") or None
    zone = None
    if zone_id:
        zone = services.zones_of(event).filter(pk=zone_id).first() if _uuid(zone_id) else None
        if zone is None:
            messages.error(request, _("Unknown zone."))
            return redirect("evacuation:index", event.slug)
    try:
        services.change(event, State.NORMAL, zone=zone, actor=request.user, request=request)
    except machine.Refused as err:
        messages.error(request, err.message)
    else:
        messages.success(request, _("Back to normal."))
    return redirect("evacuation:index", event.slug)


def _uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


@event_view("evacuation.view", module=MODULE)
def history(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    cfg = services.config(event)
    rows = StateChange.objects.filter(event=event).select_related("actor")
    if request.GET.get("drills") == "only":
        rows = rows.filter(drill=True)
    elif request.GET.get("drills") == "none":
        rows = rows.filter(drill=False)
    return render(request, "evacuation/history.html", {"event": event, "history": rows[:500], "labels": cfg.labels,
                                                       "filter": request.GET.get("drills", "")})
