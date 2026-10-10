# SPDX-License-Identifier: AGPL-3.0-or-later
"""Access pages: attendees (list, import, export, one attendee), ticket types with their badge layout, access
zones, the badge print sheet; the check-in stations and the scanner page with its offline list and batch sync."""
from __future__ import annotations

import csv
import json
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import badges, panels, services
from .forms import AttendeeForm, ImportForm, TicketTypeForm, ZoneForm
from .models import AccessZone, Attendee, Scan, TicketType

MODULE = "access"


def _fail(request: Any, err: ValidationError) -> None:
    for m in err.messages:
        messages.error(request, m)


def _tz(event: Any) -> Any:
    import zoneinfo

    try:
        return zoneinfo.ZoneInfo(event.timezone or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return zoneinfo.ZoneInfo("UTC")


def _attendees(request: Any, event: Any) -> Any:
    qs = Attendee.objects.filter(event=event).select_related("ticket_type")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(company__icontains=q) | Q(code=q))
    t = request.GET.get("type") or ""
    if len(t) == 36:
        qs = qs.filter(ticket_type_id=t)
    st = request.GET.get("status") or ""
    if st == "in":
        qs = qs.filter(checked_in_at__isnull=False)
    elif st == "out":
        qs = qs.filter(checked_in_at__isnull=True, status=Attendee.Status.VALID)
    elif st in Attendee.Status.values:
        qs = qs.filter(status=st)
    return qs


@event_view("access.view", module=MODULE)
def index(request, slug, *, event):
    with timezone.override(_tz(event)):
        return render(request, "access/index.html", {
            "event": event, "stats": services.stats(event), "attendees": _attendees(request, event)[:500],
            "types": TicketType.objects.filter(event=event), "q": request.GET.get("q", ""),
            "type": request.GET.get("type", ""), "status": request.GET.get("status", ""),
            "can_manage": rbac.has_any(request.user, event, "access.manage", request=request),
            "recent": Scan.objects.filter(event=event).select_related("zone", "attendee")[:12],
            "sources": _sources(event)})


def _sources(event: Any) -> list[dict[str, Any]]:
    """Ticket sources of the event: extensions with an "attendees" feature (pretix) offer “Sync now” at
    ``<settings page>x/sync/``."""
    from apps.extensions.models import ExtensionConfig

    out = []
    for c in ExtensionConfig.objects.filter(event=event, enabled=True).order_by("extension"):
        spec = c.spec
        if spec is None or not any(f.key == "attendees" for f in spec.features):
            continue
        detail = reverse("extensions:event_detail", args=[event.slug, c.extension])
        out.append({"config": c, "name": spec.name, "detail": detail, "sync": f"{detail}x/sync/"})
    return out


@event_view("access.view", module=MODULE)
def export(request, slug, *, event):
    if not rbac.has_any(request.user, event, "access.manage", request=request):
        raise PermissionDenied("access.manage")
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{event.slug}-attendees.csv"'
    w = csv.writer(resp)
    w.writerow(["name", "email", "company", "ticket_type", "code", "status", "checked_in_at"])
    for a in _attendees(request, event):
        row = [a.name, a.email, a.company, a.ticket_type.name, a.code, a.status,
               a.checked_in_at.isoformat() if a.checked_in_at else ""]
        # no spreadsheet formulas from user text
        w.writerow([f"'{v}" if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v for v in row])
    return resp


@event_view("access.manage", module=MODULE)
def import_view(request, slug, *, event):
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        f = form.cleaned_data["file"]
        if f.size > 10 * 1024 * 1024:
            messages.error(request, _("The file is larger than 10 MB."))
        else:
            try:
                st = services.import_csv(event, f.read(), actor=request.user, request=request)
            except ValidationError as err:
                _fail(request, err)
            else:
                messages.success(request, _("%(a)s added, %(u)s updated, %(s)s skipped, %(t)s new ticket types.")
                                 % {"a": st["added"], "u": st["updated"], "s": st["skipped"], "t": st["types"]})
                return redirect("access:index", slug)
    return render(request, "access/form.html", {"event": event, "form": form, "title": _("Import attendees"),
                                                "files": True, "back": reverse("access:index", args=[slug])})


@event_view("access.view", module=MODULE)
def attendee(request, slug, pk=None, *, event):
    a = get_object_or_404(Attendee.objects.select_related("ticket_type"), event=event, pk=pk) if pk else None
    can_manage = rbac.has_any(request.user, event, "access.manage", request=request)
    form = AttendeeForm(request.POST or None, instance=a or Attendee(event=event), event=event) if can_manage \
        else None
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied("access.manage")
        if request.POST.get("status"):
            if a is not None:
                services.set_status(a, request.POST["status"], actor=request.user, request=request)
            return redirect("access:attendee", slug, a.pk) if a else redirect("access:index", slug)
        if form is not None and form.is_valid():
            try:
                obj = services.save_attendee(form.save(commit=False), actor=request.user, request=request)
            except ValidationError as err:
                _fail(request, err)
            else:
                messages.success(request, _("Saved."))
                return redirect("access:attendee", slug, obj.pk)
    if a is None and not can_manage:
        raise PermissionDenied("access.manage")
    from apps.accounts.twofactor import qr_svg

    with timezone.override(_tz(event)):
        return render(request, "access/attendee.html", {
            "event": event, "a": a, "form": form, "can_manage": can_manage,
            "qr": qr_svg(a.code) if a else "", "presence": a.presence.select_related("zone") if a else [],
            "scans": a.scans.select_related("zone")[:50] if a else []})


@event_view("access.view", module=MODULE)
def types(request, slug, *, event):
    can_manage = rbac.has_any(request.user, event, "access.manage", request=request)
    form = TicketTypeForm(request.POST or None, instance=TicketType(event=event), event=event, prefix="t") \
        if can_manage else None
    zone = ZoneForm(request.POST or None, instance=AccessZone(event=event), event=event, prefix="z") \
        if can_manage else None
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied("access.manage")
        what = request.POST.get("what")
        if what == "type" and form is not None and form.is_valid():
            form.save()
            messages.success(request, _("Ticket type added."))
            return redirect("access:types", slug)
        if what == "zone" and zone is not None and zone.is_valid():
            zone.save()
            messages.success(request, _("Access zone added."))
            return redirect("access:types", slug)
    from django.db.models import Count

    return render(request, "access/types.html", {
        "event": event, "can_manage": can_manage, "form": form if request.POST.get("what") != "zone" else
        TicketTypeForm(instance=TicketType(event=event), event=event, prefix="t"),
        "zone_form": zone if request.POST.get("what") != "type" else
        ZoneForm(instance=AccessZone(event=event), event=event, prefix="z"),
        "types": TicketType.objects.filter(event=event).annotate(n=Count("attendees")).prefetch_related("zones")
        .select_related("badge_layout"),
        "zones": AccessZone.objects.filter(event=event).prefetch_related("ticket_types").select_related("room"),
        "areas": dict(_area_names(event))})


def _area_names(event: Any) -> list[tuple[str, str]]:
    from .forms import area_choices

    return area_choices(event)


@event_view("access.manage", module=MODULE)
def type_edit(request, slug, pk, *, event):
    t = get_object_or_404(TicketType, event=event, pk=pk)
    form = TicketTypeForm(request.POST or None, instance=t, event=event)
    if request.method == "POST":
        if request.POST.get("badge") == "create":
            layout = badges.create_layout(t, actor=request.user, request=request)
            messages.success(request, _("Badge layout created: edit it like any layout."))
            return redirect("content:layout_edit", slug, layout.pk)
        if request.POST.get("delete"):
            if t.attendees.exists():
                messages.error(request, _("Attendees still have this ticket type."))
                return redirect("access:type", slug, t.pk)
            t.delete()
            return redirect("access:types", slug)
        if form.is_valid():
            form.save()
            messages.success(request, _("Saved."))
            return redirect("access:types", slug)
    return render(request, "access/type.html", {"event": event, "form": form, "t": t})


@event_view("access.manage", module=MODULE)
def zone_edit(request, slug, pk, *, event):
    z = get_object_or_404(AccessZone, event=event, pk=pk)
    form = ZoneForm(request.POST or None, instance=z, event=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Saved."))
        return redirect("access:types", slug)
    return render(request, "access/form.html", {"event": event, "form": form, "title": z.name,
                                                "back": reverse("access:types", args=[slug])})


@event_view("access.manage", module=MODULE)
def badges_view(request, slug, *, event):
    """The print sheet: badges of one attendee, one ticket type, or everyone not printed yet."""
    qs = Attendee.objects.filter(event=event, status=Attendee.Status.VALID).select_related(
        "ticket_type", "ticket_type__badge_layout").prefetch_related("ticket_type__zones")
    if len(request.GET.get("attendee") or "") == 36:
        qs = qs.filter(pk=request.GET["attendee"])
    elif len(request.GET.get("type") or "") == 36:
        qs = qs.filter(ticket_type_id=request.GET["type"])
    if request.GET.get("new") == "1":
        qs = qs.filter(badge_printed_at__isnull=True)
    people = list(qs[:300])
    if request.method == "POST":
        Attendee.objects.filter(pk__in=[a.pk for a in people]).update(badge_printed_at=timezone.now())
        messages.success(request, _("%(n)s badges marked as printed.") % {"n": len(people)})
        return redirect("access:index", slug)
    from apps.accounts.twofactor import qr_svg

    groups, plain = [], []
    by_layout: dict[Any, list[Attendee]] = {}
    for a in people:
        if a.ticket_type.badge_layout_id:
            by_layout.setdefault(a.ticket_type.badge_layout, []).append(a)
        else:
            plain.append({"a": a, "qr": qr_svg(a.code), "zones": ", ".join(z.name for z in a.ticket_type.zones.all())})
    for layout, members in by_layout.items():
        groups.append({"layout": layout, "config": badges.sheet_config(event, layout, members), "n": len(members)})
    from apps.content.layout_views import editor_version

    return render(request, "access/badges.html", {"event": event, "groups": groups, "plain": plain,
                                                  "count": len(people), "editor_version": editor_version()})


# ------------------------------------------------------------------ check-in
@event_view("access.scan", module=MODULE)
def stations(request, slug, *, event):
    return render(request, "access/stations.html", {"event": event, "zones": panels.scan_zones(request, event)})


def _scan_zone(request: Any, event: Any, pk: Any) -> AccessZone:
    z = get_object_or_404(AccessZone, event=event, pk=pk)
    if not rbac.has_perm(request.user, event, "access.scan", obj=z, request=request):
        raise PermissionDenied("access.scan")
    return z


@event_view("access.scan", module=MODULE)
def scanner(request, slug, pk, *, event):
    z = _scan_zone(request, event, pk)
    direction = "out" if request.GET.get("dir") == "out" else "in"
    return render(request, "access/scanner.html", {
        "event": event, "zone": z, "direction": direction,
        "refresh": int(services.access_settings(event).get("list_refresh_seconds") or 60)})


@event_view("access.scan", module=MODULE)
def scan_list(request, slug, pk, *, event):
    z = _scan_zone(request, event, pk)
    resp = JsonResponse(services.offline_list(z))
    resp["Cache-Control"] = "private, no-store"
    return resp


@require_POST
@event_view("access.scan", module=MODULE)
def scan_sync(request, slug, *, event):
    """The scanner's batch: ``{"scans": [...]}`` (queued scans, oldest first); answers each scan's result."""
    try:
        body = json.loads(request.body or b"{}")
        items = body.get("scans") if isinstance(body, dict) else None
        if not isinstance(items, list) or len(items) > services.MAX_BATCH:
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "send {\"scans\": [...]}"}, status=400)
    results = services.batch(event, items, actor=request.user, can_scan=lambda z: rbac.has_perm(
        request.user, event, "access.scan", obj=z, request=request))
    return JsonResponse({"results": results})
