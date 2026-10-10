# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venue pages within an event: list the event's venues, add/link venues, edit buildings/floors/zones/rooms."""
from __future__ import annotations

import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.core.audit import log
from apps.events import rbac
from apps.portal.forms import VenueForm
from apps.portal.shortcuts import event_view

from . import access, forms, graph, mapdata, plans
from .models import Building, Edge, Floor, Point, Room, Venue, Zone

PARTS = {
    "building": (Building, forms.BuildingForm, gettext_lazy("Building")),
    "floor": (Floor, forms.FloorForm, gettext_lazy("Floor")),
    "zone": (Zone, forms.ZoneForm, gettext_lazy("Zone")),
    "room": (Room, forms.RoomForm, gettext_lazy("Room")),
    "point": (Point, forms.PointForm, gettext_lazy("Exit, assembly point or waypoint")),
    "edge": (Edge, forms.EdgeForm, gettext_lazy("Route connection")),
}
NEEDS_VENUE = ("floor", "room", "point", "edge")


def _venue(request, event, venue_slug):
    venue = get_object_or_404(event.venues, slug=venue_slug)
    if not rbac.has_perm(request.user, event, "venues.view", obj=venue, request=request):
        raise PermissionDenied
    return venue


@event_view("venues.view", module="venues")
def index(request, slug, *, event):
    access_info = rbac.effective(request.user, event, request=request).access
    scopes = access_info.scopes_for("venues.view")
    venues = [v for v in event.venues.all() if scopes is None or ("venue", str(v.pk)) in scopes]
    can_add = access_info.allows("venues.manage")
    form = VenueForm(request.POST or None, prefix="new") if can_add else None
    linkable = Venue.objects.exclude(events=event) if request.user.is_superuser else Venue.objects.none()
    if request.method == "POST" and can_add:
        if request.POST.get("link"):
            venue = get_object_or_404(linkable, pk=request.POST["link"])
            event.venues.add(venue)
            log(action="venue.linked", actor=request.user, target=venue, event=event, request=request)
            return redirect("venues:index", slug)
        if form.is_valid():
            venue = form.save()
            event.venues.add(venue)
            log(action="venue.created", actor=request.user, target=venue, event=event, request=request)
            messages.success(request, _("Venue added."))
            return redirect("venues:detail", slug, venue.slug)
    return render(request, "venues/index.html", {"event": event, "venues": venues, "form": form,
                                                 "linkable": linkable, "can_add": can_add})


@event_view("venues.view", module="venues")
def detail(request, slug, venue_slug, *, event):
    venue = _venue(request, event, venue_slug)
    can_edit = rbac.has_perm(request.user, event, "venues.manage", obj=venue, request=request)
    part_forms = {}
    if can_edit:
        for key, (_model, form_cls, label) in PARTS.items():
            kwargs = {"venue": venue} if key in NEEDS_VENUE else {}
            bound = request.method == "POST" and request.POST.get("part") == key
            part_forms[key] = (label, form_cls(request.POST if bound else None, prefix=key, **kwargs))
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if request.POST.get("part") == "venue":
            vform = VenueForm(request.POST, instance=venue, prefix="venue")
            if vform.is_valid():
                vform.save()
                log(action="venue.updated", actor=request.user, target=venue, event=event, request=request,
                    changes={f: ["", str(vform.cleaned_data[f])] for f in vform.changed_data})
                messages.success(request, _("Venue saved."))
                return redirect("venues:detail", slug, venue.slug)
        elif request.POST.get("part") in PARTS:
            label, form = part_forms[request.POST["part"]]
            if form.is_valid():
                obj = form.save(commit=False)
                if hasattr(obj, "venue_id") and not isinstance(obj, Floor):
                    obj.venue = venue
                obj.save()
                form.save_m2m()
                log(action="venue.part_created", actor=request.user, target=obj, event=event, request=request,
                    message=f"{label} {obj} added to {venue}")
                messages.success(request, _("%(what)s added.") % {"what": label})
                return redirect("venues:detail", slug, venue.slug)
    return render(request, "venues/detail.html", {
        "event": event, "venue": venue, "can_edit": can_edit, "part_forms": part_forms,
        "venue_form": VenueForm(instance=venue, prefix="venue") if can_edit else None,
        "buildings": venue.buildings.prefetch_related("floors"), "zones": venue.zones.all(),
        "rooms": venue.rooms.select_related("floor__building").prefetch_related("zones"),
        "shared_with": venue.events.exclude(pk=event.pk).count(),
        "points": venue.points.select_related("floor__building", "zone", "room"),
        "edges": venue.edges.select_related("a", "b"), "routes": graph.report(venue),
    })


@require_POST
@event_view("venues.view", module="venues")
def part_delete(request, slug, venue_slug, part, pk, *, event):
    venue = _venue(request, event, venue_slug)
    if part not in PARTS:
        raise PermissionDenied
    model = PARTS[part][0]
    lookup = {"building__venue": venue} if model is Floor else {"venue": venue}
    obj = get_object_or_404(model, pk=pk, **lookup)
    if not access.allowed(request.user, obj, "venues.manage", request) or not rbac.has_perm(
            request.user, event, "venues.manage", obj=obj, request=request):
        raise PermissionDenied
    log(action="venue.part_deleted", actor=request.user, target=obj, event=event, request=request,
        message=f"{PARTS[part][2]} {obj} removed from {venue}")
    obj.delete()
    messages.success(request, _("Removed."))
    return redirect("venues:detail", slug, venue.slug)


# ------------------------------------------------------------------ map editor (ADR-0027)
MAP_STRINGS = [
    "Select", "Add point", "Connect", "Zone outline", "Place", "Measure", "Fit", "Zoom in", "Zoom out", "Delete",
    "Name", "Kind", "Step-free", "One way", "Facing", "Remove from map", "Finish outline", "Clear outline",
    "Cancel", "Zone", "Metres", "Set scale", "Saved", "Saving…", "Could not save", "No floor plan",
    "Not on this map", "On this floor", "Click on the map to place it.", "Click two points to connect them.",
    "Click the corners, then Finish outline.", "Click two ends of a known distance.", "Distance in metres",
    "Drag points to move them. Arrows show the way out.", "No way out", "elsewhere", "Choose a zone",
    "Choose what to place", "Layers", "Points", "Outdoors", "Next step", "Plan not measured yet", "Tools", "Map",
    "Loading…", "Align with map", "Latitude", "Longitude", "Rotation (°)", "Apply", "Plan opacity",
    "Download area for offline use", "Drag the map until it matches the plan.",
    "Enter the position of the plan's top-left corner.",
]


def _manage(request, event, venue) -> bool:
    return rbac.has_perm(request.user, event, "venues.manage", obj=venue, request=request)


@event_view("venues.view", module="venues")
def map_editor(request, slug, venue_slug, *, event):
    venue = _venue(request, event, venue_slug)
    floor_id = request.GET.get("floor", "")
    floors = mapdata.floors(venue)
    if floor_id == "" and floors:
        floor_id = str(next((f for f in floors if f.plan_file), floors[0]).pk)
    try:
        floor = mapdata.floor_of(venue, floor_id)
    except ValidationError:
        raise Http404 from None
    can_edit = _manage(request, event, venue)
    base = reverse("venues:map", args=[slug, venue.slug])
    query = f"?floor={floor.pk if floor else 'outdoors'}"
    config = {"dataUrl": reverse("venues:map_data", args=[slug, venue.slug]) + query,
              "opUrl": reverse("venues:map_op", args=[slug, venue.slug]) + query,
              "strings": {s: _(s) for s in MAP_STRINGS}}
    return render(request, "venues/map.html", {
        "event": event, "venue": venue, "floors": floors, "floor": floor, "floor_id": floor_id or "outdoors",
        "can_edit": can_edit, "config": config, "base": base, "pdf": plans.has_pdf_renderer(),
        "map_version": map_version(),
    })


@event_view("venues.view", module="venues")
def map_data(request, slug, venue_slug, *, event):
    venue = _venue(request, event, venue_slug)
    try:
        floor = mapdata.floor_of(venue, request.GET.get("floor", ""))
    except ValidationError:
        raise Http404 from None
    return JsonResponse(mapdata.data(event, venue, floor, can_edit=_manage(request, event, venue)))


@require_POST
@event_view("venues.view", module="venues")
def map_op(request, slug, venue_slug, *, event):
    venue = _venue(request, event, venue_slug)
    if not _manage(request, event, venue):
        return JsonResponse({"ok": False, "error": _("You may not edit this venue.")}, status=403)
    try:
        op = json.loads(request.body or b"{}")
        if not isinstance(op, dict):
            raise ValueError
        floor = mapdata.floor_of(venue, request.GET.get("floor", ""))
        result = mapdata.apply(event, venue, floor, op, actor=request.user, request=request)
    except ValueError:
        return JsonResponse({"ok": False, "error": _("Malformed request.")}, status=400)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": " ".join(exc.messages)}, status=400)
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "error": str(exc) or _("Not allowed.")}, status=403)
    return JsonResponse({"ok": True, **result})


@require_POST
@event_view("venues.view", module="venues")
def plan_upload(request, slug, venue_slug, floor_id, *, event):
    venue = _venue(request, event, venue_slug)
    if not _manage(request, event, venue):
        raise PermissionDenied
    floor = get_object_or_404(Floor, building__venue=venue, pk=floor_id)
    if request.POST.get("remove"):
        plans.remove(floor, actor=request.user, request=request, event=event)
        messages.success(request, _("Floor plan removed."))
    elif request.FILES.get("plan"):
        try:
            plans.store(floor, request.FILES["plan"], actor=request.user, request=request, event=event)
        except ValidationError as exc:
            for m in exc.messages:
                messages.error(request, m)
        else:
            messages.success(request, _("Floor plan uploaded. Measure a known distance to set the scale."))
    return redirect(f"{reverse('venues:map', args=[slug, venue.slug])}?floor={floor.pk}")


@event_view("venues.view", module="venues")
def plan_file(request, slug, venue_slug, floor_id, *, event):
    venue = _venue(request, event, venue_slug)
    floor = get_object_or_404(Floor, building__venue=venue, pk=floor_id)
    path = plans.path_of(floor)
    if path is None:
        raise Http404
    response = FileResponse(open(path, "rb"), content_type="image/svg+xml" if path.suffix == ".svg" else "image/png")
    response["Cache-Control"] = "private, max-age=86400"
    response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def map_version() -> str:
    import hashlib

    from django.conf import settings

    h = hashlib.sha256()
    for name in ("mapeditor.js", "mapeditor.css"):
        p = settings.BASE_DIR / "static" / "mapeditor" / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


# ------------------------------------------------------------------ map tiles (ADR-0028)
def tile(request, z, x, y):
    """A cached map tile. A missing one is fetched in the background (never inside the request): 503 and the
    editor retries."""
    from django.contrib.auth.views import redirect_to_login
    from django.core.cache import cache
    from django.http import HttpResponse

    from . import geo, tasks

    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not geo.valid_tile(z, x, y) or not geo.config().get("tiles_enabled") or not geo.tile_url():
        raise Http404
    if z > int(geo.config().get("max_zoom") or 19):
        raise Http404
    path = geo.tile_path(z, x, y)
    if path.exists():
        head = path.read_bytes()[:4]
        response = FileResponse(open(path, "rb"), content_type="image/jpeg" if head[:2] == b"\xff\xd8" else (
            "image/webp" if head == b"RIFF" else "image/png"))
        response["Cache-Control"] = "private, max-age=604800"
        return response
    if cache.add(f"evac:tile:{z}/{x}/{y}", 1, 60):
        tasks.fetch_tile.delay(z, x, y)
    response = HttpResponse(status=503)
    response["Retry-After"] = "2"
    response["Cache-Control"] = "no-store"
    return response
