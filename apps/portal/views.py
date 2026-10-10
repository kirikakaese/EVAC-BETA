# SPDX-License-Identifier: AGPL-3.0-or-later
"""Portal: home, first-run wizard, events (dashboard, settings, lifecycle, clone, export/import)."""
from __future__ import annotations

import json
import os
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.core import modules
from apps.core.audit import log
from apps.core.middleware import FirstRunMiddleware
from apps.core.models import AuditLog
from apps.events import rbac, services
from apps.events.models import Event, ScheduledTransition
from apps.venues.models import Venue

from . import forms
from .shortcuts import event_view, superuser_view


def home(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    events = list(Event.objects.visible_to(request.user).prefetch_related("venues"))
    if len(events) == 1 and not request.user.is_superuser:
        return redirect("portal:event_dashboard", events[0].slug)
    return render(request, "portal/home.html", {"events": events})


def about(request):
    return render(request, "portal/about.html")


# --------------------------------------------------------------------------- first-run wizard

SETUP_STEPS = ("admin", "venue", "event", "screen", "done")


def _setup_token() -> str:
    return os.environ.get("EVAC_SETUP_TOKEN", "")


def setup(request):
    """First-run wizard: admin account -> venue -> event -> first screen (Phase 1) -> welcome."""
    has_users = User.objects.exists()
    step = request.GET.get("step") or ("admin" if not has_users else request.session.get("evac_setup_step", ""))
    allowed = request.user.is_authenticated and request.user.is_superuser and step in SETUP_STEPS[1:]
    if has_users and not allowed:
        return redirect("portal:home")
    if step == "admin":
        if has_users:
            return redirect("portal:home")
        token = _setup_token()
        form = forms.SetupAdminForm(request.POST or None, token_required=bool(token))
        if request.method == "POST" and form.is_valid():
            if token and form.cleaned_data.get("setup_token") != token:
                form.add_error("setup_token", _("Wrong setup token."))
            else:
                with transaction.atomic():
                    if User.objects.select_for_update().exists():
                        return redirect("portal:home")
                    user = User.objects.create_superuser(email=form.cleaned_data["email"].lower(),
                                                         password=form.cleaned_data["password1"],
                                                         display_name=form.cleaned_data["display_name"])
                    log(action="setup.admin_created", actor=user, target=user, request=request,
                        message="First instance admin created by the setup wizard")
                cache.delete(FirstRunMiddleware.CACHE_KEY)
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                request.session["evac_setup_step"] = "venue"
                return redirect(reverse("portal:setup") + "?step=venue")
        return render(request, "portal/setup.html", {"step": step, "form": form, "steps": SETUP_STEPS})
    if step == "venue":
        form = forms.VenueForm(request.POST or None, prefix="venue")
        if request.method == "POST":
            if "skip" in request.POST:
                request.session["evac_setup_step"] = "event"
                return redirect(reverse("portal:setup") + "?step=event")
            if form.is_valid():
                venue = form.save()
                log(action="venue.created", actor=request.user, target=venue, request=request)
                request.session["evac_setup_venue"] = str(venue.pk)
                request.session["evac_setup_step"] = "event"
                return redirect(reverse("portal:setup") + "?step=event")
        return render(request, "portal/setup.html", {"step": step, "form": form, "steps": SETUP_STEPS})
    if step == "event":
        venue = Venue.objects.filter(pk=request.session.get("evac_setup_venue")).first()
        form = forms.SetupEventForm(request.POST or None, initial={"timezone": venue.timezone if venue else "UTC"})
        if request.method == "POST" and form.is_valid():
            data = {k: v for k, v in form.cleaned_data.items() if k not in ("name", "slug")
                    and not k.startswith("use_")}
            event = services.create_event(name=form.cleaned_data["name"], slug=form.cleaned_data["slug"],
                                          user=request.user, request=request, **data)
            if venue is not None:
                event.venues.add(venue)
            for key in form.modules_to_enable():
                modules.acknowledge(event, key, user=request.user, request=request)
                if not modules.instance_enabled(key):
                    modules.set_instance(key, True, user=request.user, request=request)
                modules.set_event(event, key, True, user=request.user, request=request)
            request.session["evac_setup_event"] = event.slug
            request.session["evac_setup_step"] = "screen"
            return redirect(reverse("portal:setup") + "?step=screen")
        return render(request, "portal/setup.html", {"step": step, "form": form, "steps": SETUP_STEPS,
                                                     "venue": venue})
    if step == "screen":
        event = Event.objects.filter(slug=request.session.get("evac_setup_event", "")).first()
        # the screens module is optional: pairing is only offered when it is installed and on for the event
        can_pair = event is not None and modules.is_enabled("screens", event)
        if request.method == "POST":
            request.session["evac_setup_step"] = "done"
            code = (request.POST.get("code") or "").strip()
            if can_pair and code and "skip" not in request.POST:
                done = reverse("portal:setup") + "?step=done"
                return redirect(reverse("screens:pair", args=[event.slug]) + "?" + urlencode(
                    {"code": code, "name": (request.POST.get("name") or "").strip()[:200], "next": done}))
            return redirect(reverse("portal:setup") + "?step=done")
        return render(request, "portal/setup.html", {"step": step, "steps": SETUP_STEPS, "event": event,
                                                     "can_pair": can_pair,
                                                     "player_url": request.build_absolute_uri("/player/")})
    slug = request.session.pop("evac_setup_event", None)
    request.session.pop("evac_setup_step", None)
    request.session.pop("evac_setup_venue", None)
    event = Event.objects.filter(slug=slug).first() if slug else None
    return render(request, "portal/setup.html", {"step": "done", "steps": SETUP_STEPS, "event": event})


# --------------------------------------------------------------------------- events

@superuser_view
def event_create(request):
    form = forms.EventForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if k not in ("name", "slug", "venues")}
        event = services.create_event(name=form.cleaned_data["name"], slug=form.cleaned_data["slug"],
                                      user=request.user, request=request, **data)
        event.venues.set(form.cleaned_data["venues"])
        messages.success(request, _("Event created."))
        return redirect("portal:event_dashboard", event.slug)
    return render(request, "portal/event_form.html", {"form": form, "creating": True})


@event_view("events.view")
def event_dashboard(request, slug, *, event):
    info = rbac.effective(request.user, event, request=request)
    recent = AuditLog.objects.for_event(event)[:10] if "audit.view" in info.permissions else []
    return render(request, "portal/event_dashboard.html", {
        "event": event, "recent": recent, "modules": [r for r in modules.status(event) if not r["spec"].required],
        "members": event.memberships.count(), "venues": event.venues.all(),
        "scheduled": event.scheduled_transitions.filter(applied_at__isnull=True, error=""),
        "can_manage": "events.manage" in info.permissions,
    })


@event_view("events.manage")
def event_settings(request, slug, *, event):
    rbac.require(request, event, "events.manage")
    form = forms.EventForm(request.POST or None, request.FILES or None, instance=event)
    if request.method == "POST" and form.is_valid():
        before = {f: str(getattr(Event.objects.get(pk=event.pk), f)) for f in form.changed_data if f != "venues"}
        obj = form.save()
        log(action="event.updated", actor=request.user, target=obj, event=obj, request=request,
            changes={f: [before.get(f), str(getattr(obj, f, ""))] for f in form.changed_data})
        from apps.core.webhooks import emit

        emit("event.updated", {"slug": obj.slug}, event=obj)
        messages.success(request, _("Event saved."))
        return redirect("portal:event_settings", obj.slug)
    from apps.core.registry import registry

    namespaces = [ns for ns in sorted(registry.ensure_loaded().settings_namespaces.values(), key=lambda n: n.order)
                  if "event" in ns.levels and modules.is_enabled(ns.module, event)]
    return render(request, "portal/event_settings.html", {
        "event": event, "form": form, "namespaces": namespaces,
        "transition_targets": [(s, Event.State(s).label) for s in Event.TRANSITIONS[event.state]],
        "schedule_form": forms.ScheduleForm(prefix="sched"),
        "clone_form": forms.CloneForm(prefix="clone", initial={"name": f"{event.name} (copy)"}),
        "scheduled": event.scheduled_transitions.all()[:20],
        "can_delete": rbac.has_perm(request.user, event, "events.delete", request=request),
    })


@require_POST
@event_view("events.manage")
def event_lifecycle(request, slug, *, event):
    if "schedule" in request.POST:
        form = forms.ScheduleForm(request.POST, prefix="sched")
        if form.is_valid():
            st = ScheduledTransition.objects.create(event=event, created_by=request.user, **form.cleaned_data)
            log(action="event.transition_scheduled", actor=request.user, target=event, event=event, request=request,
                message=str(st))
            messages.success(request, _("Transition scheduled."))
        else:
            messages.error(request, _("Please give a target state and a time."))
        return redirect("portal:event_settings", slug)
    if "cancel" in request.POST:
        st = get_object_or_404(ScheduledTransition, pk=request.POST["cancel"], event=event, applied_at__isnull=True)
        log(action="event.transition_unscheduled", actor=request.user, target=event, event=event, request=request,
            message=str(st))
        st.delete()
        return redirect("portal:event_settings", slug)
    form = forms.TransitionForm(request.POST)
    if form.is_valid():
        target = form.cleaned_data["state"]
        perm = "events.delete" if target == Event.State.ARCHIVED else "events.manage"
        if not rbac.has_perm(request.user, event, perm, request=request):
            raise PermissionDenied(perm)
        try:
            event.transition(target, user=request.user, request=request, reason=form.cleaned_data["reason"])
            messages.success(request, _("The event is now %(state)s.") % {"state": event.get_state_display()})
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    return redirect("portal:event_settings", slug)


@require_POST
@event_view("events.manage")
def event_clone(request, slug, *, event):
    if not request.user.is_superuser:
        raise PermissionDenied
    form = forms.CloneForm(request.POST, prefix="clone")
    if not form.is_valid():
        messages.error(request, _("Please give the new event a name."))
        return redirect("portal:event_settings", slug)
    try:
        dst = services.clone_event(event, user=request.user, request=request, **form.cleaned_data)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("portal:event_settings", slug)
    messages.success(request, _("Event cloned."))
    return redirect("portal:event_dashboard", dst.slug)


@event_view("events.manage")
def event_export(request, slug, *, event):
    log(action="event.exported", actor=request.user, target=event, event=event, request=request)
    resp = JsonResponse(services.export_event(event), json_dumps_params={"indent": 2})
    resp["Content-Disposition"] = f'attachment; filename="evac-{event.slug}-{timezone.now():%Y%m%d}.json"'
    return resp


@superuser_view
def event_import(request):
    form = forms.ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            data = json.loads(form.cleaned_data["file"].read().decode("utf-8"))
            event, report = services.import_event(data, slug=form.cleaned_data["slug"], name=form.cleaned_data["name"],
                                                  user=request.user, request=request)
        except (ValueError, UnicodeDecodeError):
            form.add_error("file", _("This file is not valid JSON."))
        except ValidationError as exc:
            form.add_error("file", exc.messages[0])
        else:
            for line in report:
                messages.warning(request, line)
            messages.success(request, _("Event imported."))
            return redirect("portal:event_dashboard", event.slug)
    return render(request, "portal/event_import.html", {"form": form})


def switch_event(request, slug):
    if not request.user.is_authenticated:
        raise Http404
    event = get_object_or_404(Event.objects.visible_to(request.user), slug=slug)
    return redirect("portal:event_dashboard", event.slug)


def search(request):
    """Global search over events, venues, members and docs the user may see."""
    q = (request.GET.get("q") or "").strip()
    results: dict[str, list] = {}
    if q and request.user.is_authenticated:
        events = Event.objects.visible_to(request.user)
        results["events"] = list(events.filter(name__icontains=q)[:10])
        from apps.venues.access import visible

        results["venues"] = list(visible(request.user, request).filter(name__icontains=q)[:10])
        from .docs import search_docs

        results["docs"] = search_docs(q)[:10]
    return render(request, "portal/search.html", {"q": q, "results": results})
