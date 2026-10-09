# SPDX-License-Identifier: AGPL-3.0-or-later
"""Portal pages: screen list with health, pairing, screen details, screen groups."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import modules
from apps.events import rbac
from apps.events.models import Event
from apps.portal.shortcuts import event_view

from . import forms, services
from .models import HEALTH_BADGE, Screen, ScreenGroup, normalize_code


def _visible(request, event, perm, objs):
    scopes = rbac.effective(request.user, event, request=request).access.scopes_for(perm)
    if scopes is None:
        return list(objs)
    allowed = set(scopes)
    return [o for o in objs if allowed & set(o.evac_scope_chain())]


def _with_health(event, screens):
    cfg = services.screen_settings(event)
    now = timezone.now()
    for s in screens:
        s.current_health = s.health(heartbeat_seconds=cfg["heartbeat_seconds"],
                                    offline_after=cfg["offline_after_seconds"], now=now)
        s.health_label = Screen.Health(s.current_health).label
        s.health_badge = HEALTH_BADGE[s.current_health]
    return screens


def _screen(request, event, pk, perm="screens.view"):
    screen = get_object_or_404(Screen.objects.select_related("venue", "zone", "room"), event=event, pk=pk)
    if not rbac.has_perm(request.user, event, perm, obj=screen, request=request):
        raise PermissionDenied(perm)
    return screen


@event_view("screens.view", module="screens")
def index(request, slug, *, event):
    qs = Screen.objects.filter(event=event).select_related("venue", "zone", "room")
    groups = _visible(request, event, "screens.view", event.screen_groups.all())
    group = None
    if request.GET.get("group"):
        group = next((g for g in groups if str(g.pk) == request.GET["group"]), None)
        if group is not None:
            qs = group.screens().select_related("venue", "zone", "room")
    screens = _with_health(event, _visible(request, event, "screens.view", qs))
    counts = {state: sum(1 for s in screens if s.current_health == state) for state in Screen.Health.values}
    return render(request, "screens/index.html", {
        "event": event, "screens": screens, "groups": groups, "group": group, "counts": counts,
        "can_pair": rbac.has_perm(request.user, event, "screens.pair", request=request),
    })


@event_view("screens.pair", module="screens")
def pair(request, slug, *, event):
    form = forms.PairForm(request.POST or None, event=event,
                          initial={"code": request.GET.get("code", ""), "screen": request.GET.get("screen")})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        existing = data["screen"]
        if existing is not None and not rbac.has_perm(request.user, event, "screens.manage", obj=existing,
                                                      request=request):
            raise PermissionDenied("screens.manage")
        try:
            screen = services.pair(event, data["code"], actor=request.user, request=request, screen=existing,
                                   name=data["name"], venue=data["venue"], zone=data["zone"], room=data["room"],
                                   groups=data["groups"], tags=data["tags"])
        except ValidationError as exc:
            form.add_error("code", exc.messages[0])
        else:
            messages.success(request, _("Screen paired. It connects within a few seconds."))
            return redirect("screens:detail", slug, screen.pk)
    return render(request, "screens/pair.html", {"event": event, "form": form})


@event_view("screens.view", module="screens")
def detail(request, slug, pk, *, event):
    screen = _screen(request, event, pk)
    can_manage = rbac.has_perm(request.user, event, "screens.manage", obj=screen, request=request)
    form = (forms.ScreenForm(request.POST or None, instance=screen, event=event, prefix="screen")
            if can_manage else None)
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied
        before = {f: getattr(screen, f) for f in ("name", "description", "venue", "zone", "room", "tags")}
        if form.is_valid():
            services.save_screen(form.save(commit=False), actor=request.user, request=request, before=before,
                                 groups=form.cleaned_data["groups"])
            messages.success(request, _("Screen saved."))
            return redirect("screens:detail", slug, screen.pk)
    _with_health(event, [screen])
    return render(request, "screens/detail.html", {
        "event": event, "screen": screen, "form": form, "can_manage": can_manage, "groups": screen.groups(),
        "can_pair": rbac.has_perm(request.user, event, "screens.pair", request=request),
        "can_control": rbac.has_perm(request.user, event, "screens.control", obj=screen, request=request),
    })


@require_POST
@event_view("screens.manage", module="screens")
def revoke(request, slug, pk, *, event):
    screen = _screen(request, event, pk, "screens.manage")
    services.revoke(screen, actor=request.user, request=request)
    messages.success(request, _("Device token revoked. The screen stops showing content and must be paired again."))
    return redirect("screens:detail", slug, screen.pk)


@require_POST
@event_view("screens.control", module="screens")
def command(request, slug, pk, name, *, event):
    screen = _screen(request, event, pk, "screens.control")
    try:
        services.command(screen, name, actor=request.user, request=request)
    except ValidationError:
        raise PermissionDenied from None
    messages.success(request, _("Sent to the screen."))
    return redirect("screens:detail", slug, screen.pk)


@require_POST
@event_view("screens.manage", module="screens")
def delete(request, slug, pk, *, event):
    screen = _screen(request, event, pk, "screens.manage")
    services.delete_screen(screen, actor=request.user, request=request)
    messages.success(request, _("Screen deleted."))
    return redirect("screens:index", slug)


@event_view("screens.view", module="screens")
def groups(request, slug, *, event):
    can_create = rbac.has_perm(request.user, event, "screens.manage", request=request)
    form = forms.ScreenGroupForm(request.POST or None, event=event, prefix="new") if can_create else None
    if request.method == "POST":
        if not can_create:
            raise PermissionDenied
        if form.is_valid():
            group = form.save(commit=False)
            group.event = event
            services.save_group(group, actor=request.user, request=request, m2m={
                f: form.cleaned_data[f] for f in ("match_venues", "match_zones", "match_rooms")})
            messages.success(request, _("Group created."))
            return redirect("screens:group", slug, group.pk)
    items = _visible(request, event, "screens.view", event.screen_groups.all())
    for g in items:
        g.screen_count = g.screens().count()
    return render(request, "screens/groups.html", {"event": event, "groups": items, "form": form})


@event_view("screens.view", module="screens")
def group(request, slug, pk, *, event):
    grp = get_object_or_404(ScreenGroup, event=event, pk=pk)
    if not rbac.has_perm(request.user, event, "screens.view", obj=grp, request=request):
        raise PermissionDenied
    can_manage = rbac.has_perm(request.user, event, "screens.manage", obj=grp, request=request)
    form = (forms.ScreenGroupForm(request.POST or None, instance=grp, event=event, prefix="group")
            if can_manage else None)
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied
        if request.POST.get("delete"):
            services.delete_group(grp, actor=request.user, request=request)
            messages.success(request, _("Group deleted."))
            return redirect("screens:groups", slug)
        if form.is_valid():
            services.save_group(form.save(commit=False), actor=request.user, request=request, m2m={
                f: form.cleaned_data[f] for f in ("match_venues", "match_zones", "match_rooms")})
            messages.success(request, _("Group saved."))
            return redirect("screens:group", slug, grp.pk)
    members = _with_health(event, list(grp.screens().select_related("venue", "zone", "room")))
    return render(request, "screens/group.html", {"event": event, "group": grp, "form": form, "screens": members,
                                                  "can_manage": can_manage})


def pair_global(request):
    """Target of the QR code on an unpaired screen: pick the event, then pair there."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    code = normalize_code(request.GET.get("code", ""))
    events = [e for e in Event.objects.visible_to(request.user).exclude(state="archived")
              if modules.is_enabled("screens", e) and rbac.has_perm(request.user, e, "screens.pair", request=request)]
    if len(events) == 1:
        return redirect(reverse("screens:pair", args=[events[0].slug]) + f"?code={code}")
    return render(request, "screens/pair_global.html", {"events": events, "code": code})
