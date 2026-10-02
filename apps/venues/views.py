# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venue pages within an event: list the event's venues, add/link venues, edit buildings/floors/zones/rooms."""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.core.audit import log
from apps.events import rbac
from apps.portal.forms import VenueForm
from apps.portal.shortcuts import event_view

from . import access, forms
from .models import Building, Floor, Room, Venue, Zone

PARTS = {
    "building": (Building, forms.BuildingForm, gettext_lazy("Building")),
    "floor": (Floor, forms.FloorForm, gettext_lazy("Floor")),
    "zone": (Zone, forms.ZoneForm, gettext_lazy("Zone")),
    "room": (Room, forms.RoomForm, gettext_lazy("Room")),
}


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
            kwargs = {"venue": venue} if key in ("floor", "room") else {}
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
