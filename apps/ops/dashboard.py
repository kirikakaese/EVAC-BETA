# SPDX-License-Identifier: AGPL-3.0-or-later
"""The control room dashboard (brief §11.3, roadmap 6.2, ADR-0039): one large-screen page made of panels that
modules contribute with ``r.dashboard_panel``. Each panel refreshes itself (htmx) every few seconds; a panel whose
module is off or whose ``context`` returns None for this user is left out."""
from __future__ import annotations

from typing import Any

from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_safe

from apps.core import modules
from apps.core.plugins import DashboardPanelSpec
from apps.core.registry import registry
from apps.events import rbac
from apps.portal.shortcuts import event_view

from .models import SEVERITY_RANK, Incident, LogEntry, Task


def _visible(request: Any, event: Any) -> list[tuple[DashboardPanelSpec, Any]]:
    out = []
    for spec in sorted(registry.ensure_loaded().dashboard_panels.values(), key=lambda s: (s.order, s.key)):
        if spec.module != "core" and not modules.is_enabled(spec.module, event):
            continue
        ctx = spec.context(request, event)
        if ctx is not None:
            out.append((spec, ctx))
    return out


@event_view("ops.view", module="ops")
def control(request, slug, *, event):
    return render(request, "ops/control.html", {"event": event, "panels": _visible(request, event),
                                                "now": timezone.now()})


@require_safe
@event_view("ops.view", module="ops")
def panel(request, slug, key, *, event):
    spec = registry.ensure_loaded().dashboard_panels.get(key)
    if spec is None or (spec.module != "core" and not modules.is_enabled(spec.module, event)):
        raise Http404
    ctx = spec.context(request, event)
    if ctx is None:
        raise Http404
    return render(request, "ops/_panel.html", {"event": event, "spec": spec, "ctx": ctx, "refreshed": True})


# ------------------------------------------------------------------ the ops module's own panels
def _incidents(request: Any, event: Any) -> dict[str, Any]:
    qs = Incident.objects.filter(event=event, status__in=Incident.OPEN).select_related("zone", "room", "assignee")
    rows = sorted(qs, key=lambda i: (-i.rank, i.created_at))
    return {"incidents": rows[:12], "total": len(rows),
            "critical": sum(1 for i in rows if i.rank >= SEVERITY_RANK["high"]),
            "unacknowledged": sum(1 for i in rows if i.status == Incident.Status.NEW),
            "can_report": rbac.has_any(request.user, event, "ops.report", request=request)}


def _log(request: Any, event: Any) -> dict[str, Any]:
    return {"entries": list(LogEntry.objects.filter(event=event).select_related("incident")[:15]),
            "can_write": rbac.has_any(request.user, event, "ops.report", request=request)}


def _tasks(request: Any, event: Any) -> dict[str, Any] | None:
    qs = Task.objects.filter(event=event, status=Task.Status.OPEN).select_related("assignee")
    return {"tasks": list(qs[:8]), "total": qs.count(), "now": timezone.now()}


def _map(request: Any, event: Any) -> dict[str, Any] | None:
    """Zones drawn from their outlines (ADR-0026) with open incidents marked: one SVG per floor that has zones."""
    from apps.venues.models import Floor, Zone

    zones = list(Zone.objects.filter(venue__in=event.venues.all()))
    if not any(z.areas for z in zones):
        return None
    open_by_zone: dict[str, list[Incident]] = {}
    for inc in Incident.objects.filter(event=event, status__in=Incident.OPEN).select_related("room"):
        ids = {str(inc.zone_id)} if inc.zone_id else set()
        if inc.room_id:
            ids |= {str(z) for z in inc.room.zones.values_list("pk", flat=True)}
        for z in ids:
            open_by_zone.setdefault(z, []).append(inc)
    floors: dict[str, dict[str, Any]] = {}
    for z in zones:
        for area in z.areas or []:
            pts = [(float(p[0]), float(p[1])) for p in area.get("points") or [] if len(p) >= 2]
            if len(pts) < 3:
                continue
            f = floors.setdefault(str(area.get("floor") or ""), {"shapes": [], "xs": [], "ys": []})
            incs = open_by_zone.get(str(z.pk), [])
            top = max((i.rank for i in incs), default=0)
            f["shapes"].append({"zone": z, "points": " ".join(f"{x:.2f},{y:.2f}" for x, y in pts),
                                "cx": f"{sum(x for x, _y in pts) / len(pts):.2f}",
                                "cy": f"{sum(y for _x, y in pts) / len(pts):.2f}",
                                "incidents": len(incs), "level": "crit" if top >= 3 else ("warn" if top else "ok")})
            f["xs"] += [x for x, _y in pts]
            f["ys"] += [y for _x, y in pts]
    names = {str(f.pk): f"{f.building.name} · {f.name}" for f in Floor.objects.filter(
        pk__in=[k for k in floors if k]).select_related("building")}
    out = []
    for key, f in floors.items():
        x0, x1, y0, y1 = min(f["xs"]), max(f["xs"]), min(f["ys"]), max(f["ys"])
        pad = max(x1 - x0, y1 - y0) * 0.05 + 1
        size = max(x1 - x0, y1 - y0) + 2 * pad
        out.append({"name": names.get(key, str(_("Site"))), "shapes": f["shapes"],
                    "viewbox": f"{x0 - pad:.2f} {y0 - pad:.2f} {x1 - x0 + 2 * pad:.2f} {y1 - y0 + 2 * pad:.2f}",
                    "font": f"{size / 28:.2f}", "stroke": f"{size / 300:.3f}"})
    return {"floors": out[:4]}


def panels() -> list[DashboardPanelSpec]:
    return [
        DashboardPanelSpec(key="ops.incidents", title=str(_("Open incidents")), template="ops/panels/incidents.html",
                           context=_incidents, module="ops", order=20, size="wide", refresh_seconds=5),
        DashboardPanelSpec(key="ops.map", title=str(_("Map")), template="ops/panels/map.html", context=_map,
                           module="ops", order=25, size="wide", refresh_seconds=15),
        DashboardPanelSpec(key="ops.log", title=str(_("Ops log")), template="ops/panels/log.html", context=_log,
                           module="ops", order=60, size="tall", refresh_seconds=5),
        DashboardPanelSpec(key="ops.tasks", title=str(_("Open tasks")), template="ops/panels/tasks.html",
                           context=_tasks, module="ops", order=70, refresh_seconds=20),
    ]
