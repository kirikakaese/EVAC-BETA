# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event setup wizard (ADR-0050): basics -> venue -> event type -> safety -> team -> screens -> done.

The event is created at the end of the first step (``/events/new/``); every later step works on the real event
(``/e/<slug>/setup/<step>/``) and can be left, skipped and resumed (the current step is kept in the session). Steps
the user may not do, or that do not apply (screens with the screens module off, safety without a module that has a
statement), are left out. Every change goes through the existing services, which write the audit log. Optional
modules are only reached through the registry and URLs (``content:templates``, ``screens:pair``).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core import modules, setup
from apps.core.audit import log
from apps.core.registry import registry
from apps.events import rbac, services
from apps.events.models import Membership

from . import forms
from .admin_views import invite_member
from .shortcuts import can_acknowledge, event_view, pair_screen_url, superuser_view
from .views import save_event_form

SESSION_KEY = "evac_event_setup"
STEPS = ("basics", "venue", "modules", "safety", "team", "screens", "done")
STEP_LABELS = {"basics": gettext_lazy("Basics"), "venue": gettext_lazy("Venue"),
               "modules": gettext_lazy("Event type"), "safety": gettext_lazy("Safety"),
               "team": gettext_lazy("Team"), "screens": gettext_lazy("Screens"), "done": gettext_lazy("Done")}

#: screen modules every preset with screens switches on
SCREENS = ("screens", "content", "playlists", "schedules", "overrides", "widgets", "packs")


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    description: str
    modules: tuple[str, ...]


PRESETS = (
    Preset("conference", gettext_lazy("Conference"),
           gettext_lazy("Talks on several stages: the program on screens, announcements, check-in, a helpdesk and "
                        "an incident log."),
           ("venues", "evacuation", *SCREENS, "program", "announcements", "ops", "access", "helpdesk")),
    Preset("festival", gettext_lazy("Festival / camp"),
           gettext_lazy("Many people on a large site: everything for operations, crew and shifts, occupancy, "
                        "inventory and evacuation."),
           ("venues", "evacuation", *SCREENS, "program", "announcements", "ops", "crowd", "access", "crew",
            "inventory", "helpdesk")),
    Preset("screens", gettext_lazy("Venue screens only"),
           gettext_lazy("Digital signage: screens, layouts, playlists and schedules - nothing else."),
           ("venues", *SCREENS)),
)
#: modules some preset decides about; presets leave every other module (extensions, third-party plugins) as it is
MANAGED = frozenset(k for p in PRESETS for k in p.modules)


# --------------------------------------------------------------------------- state

def _state(request, event) -> dict:
    return dict((request.session.get(SESSION_KEY) or {}).get(event.slug) or {})


def _save_state(request, event, **changes) -> None:
    allstate = dict(request.session.get(SESSION_KEY) or {})
    current = dict(allstate.get(event.slug) or {})
    current.update(changes)
    allstate[event.slug] = current
    request.session[SESSION_KEY] = allstate


def _clear_state(request, event) -> None:
    allstate = dict(request.session.get(SESSION_KEY) or {})
    if allstate.pop(event.slug, None) is not None:
        request.session[SESSION_KEY] = allstate


def _perm(request, event, perm: str) -> bool:
    return rbac.has_perm(request.user, event, perm, request=request)


def _togglable():
    return [s for s in sorted(registry.ensure_loaded().modules.values(), key=lambda s: (s.order, s.name))
            if not s.required and s.event_toggle]


def _safety_keys(request, event) -> list[str]:
    """Modules with a statement this wizard has to ask about: chosen in the event type step (pending) or already on
    for the event."""
    pending = set(_state(request, event).get("pending") or [])
    return [s.key for s in _togglable() if s.acknowledgement and (s.key in pending or modules.is_enabled(s.key, event))]


def _can_screens(request, event) -> tuple[bool, bool]:
    """(may use a layout template, may pair a screen)"""
    return (modules.is_enabled("content", event) and _perm(request, event, "content.edit"),
            modules.is_enabled("screens", event) and _perm(request, event, "screens.pair"))


def steps_for(request, event) -> list[str]:
    out = ["basics"]
    if modules.is_enabled("venues", event):
        out.append("venue")
    if _perm(request, event, "modules.manage"):
        out.append("modules")
    if any(can_acknowledge(request, event, k) for k in _safety_keys(request, event)):
        out.append("safety")
    if _perm(request, event, "events.members"):
        out.append("team")
    if any(_can_screens(request, event)):
        out.append("screens")
    out.append("done")
    return out


def _url(event, step: str) -> str:
    return reverse("portal:event_setup_step", args=[event.slug, step])


def _next(request, event, step: str):
    steps = steps_for(request, event)
    later = [s for s in STEPS[STEPS.index(step) + 1:] if s in steps]
    return redirect(_url(event, later[0] if later else "done"))


def _progress(steps: list[str], current: str) -> list[dict]:
    idx = steps.index(current) if current in steps else 0
    return [{"key": s, "label": STEP_LABELS[s], "current": s == current, "done": i < idx}
            for i, s in enumerate(steps)]


def _render(request, event, step: str, steps: list[str], **ctx):
    idx = steps.index(step)
    back = _url(event, steps[idx - 1]) if idx > 0 else ""
    return render(request, "portal/event_setup.html", {
        "event": event, "step": step, "progress": _progress(steps, step), "back": back,
        "step_number": idx + 1, "step_count": len(steps), **ctx})


# --------------------------------------------------------------------------- views

@superuser_view
def create(request):
    """Step 1 for a new event: basics. The event exists after this step; "skip" goes straight to its overview."""
    form = forms.EventBasicsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if k not in ("name", "slug")}
        event = services.create_event(name=form.cleaned_data["name"], slug=form.cleaned_data["slug"],
                                      user=request.user, request=request, **data)
        messages.success(request, _("Event created."))
        if "skip_wizard" in request.POST:
            return redirect("portal:event_dashboard", event.slug)
        _save_state(request, event, step="basics")
        return _next(request, event, "basics")
    steps = ["basics", "venue", "modules", "team", "screens", "done"]
    return render(request, "portal/event_setup.html", {
        "step": "basics", "creating": True, "form": form, "progress": _progress(steps, "basics"),
        "step_number": 1, "step_count": len(steps)})


@event_view("events.manage")
def resume(request, slug, *, event):
    """Continue where this session left the wizard for the event (the first later step otherwise)."""
    step = _state(request, event).get("step") or ""
    steps = steps_for(request, event)
    if step in steps:
        return redirect(_url(event, step))
    return redirect(_url(event, steps[1] if len(steps) > 1 else "done"))


@event_view("events.manage")
def step_view(request, slug, step, *, event):
    if step not in STEPS:
        raise Http404
    steps = steps_for(request, event)
    if step not in steps:  # not applicable or not allowed for this user: go on with the next one
        return _next(request, event, step)
    if step != "done":
        _save_state(request, event, step=step)
    if request.method == "POST" and "skip" in request.POST:
        if step == "safety":
            _save_state(request, event, pending=[])
            messages.info(request, _("Not switched on. You can do it later under Settings → Modules."))
        return _next(request, event, step)
    return STEP_VIEWS[step](request, event, steps)


def _basics(request, event, steps):
    form = forms.EventBasicsForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        if form.has_changed():
            save_event_form(request, form)
        return _next(request, event, "basics")
    return _render(request, event, "basics", steps, form=form)


def _venue(request, event, steps):
    form = forms.SetupVenuesForm(request.POST or None, event=event, user=request.user)
    can_create = _perm(request, event, "venues.manage")
    wants_new = bool(can_create and request.method == "POST" and (request.POST.get("venue-name") or "").strip())
    new = forms.VenueForm(request.POST if wants_new else None, prefix="venue",
                          initial={"timezone": event.timezone}) if can_create else None
    if request.method == "POST" and form.is_valid() and (not wants_new or new.is_valid()):
        chosen = set(form.cleaned_data["venues"])
        current = set(event.venues.all())
        for venue in chosen - current:
            event.venues.add(venue)
            log(action="venue.linked", actor=request.user, target=venue, event=event, request=request)
        for venue in current - chosen:  # the choices always include the linked venues
            event.venues.remove(venue)
            log(action="venue.unlinked", actor=request.user, target=venue, event=event, request=request)
        if wants_new:
            venue = new.save()
            event.venues.add(venue)
            log(action="venue.created", actor=request.user, target=venue, event=event, request=request)
            messages.success(request, _("Venue %(name)s added.") % {"name": venue.name})
        return _next(request, event, "venue")
    return _render(request, event, "venue", steps, form=form, new=new)


def _module_rows(request, event) -> list[dict]:
    rows = []
    for spec in _togglable():
        rows.append({"spec": spec, "active": modules.is_enabled(spec.key, event),
                     "blocked": modules.blocked_reason(spec.key, request.user),
                     "instance_off": not modules.instance_enabled(spec.key),
                     "needs": [reg.name for d in spec.depends_on
                               if (reg := registry.modules.get(d)) is not None and not reg.required]})
    return rows


def _modules(request, event, steps):
    rows = _module_rows(request, event)
    by_key = {r["spec"].key: r for r in rows}
    presets = [{"preset": p, "modules": [by_key[k] for k in p.modules if k in by_key]} for p in PRESETS]
    state = _state(request, event)
    if request.method == "POST":
        choice = request.POST.get("preset", "")
        preset = next((p for p in PRESETS if p.key == choice), None)
        if preset is not None:
            keep = {r["spec"].key for r in rows if r["spec"].key not in MANAGED and r["active"]}
            wanted = set(preset.modules) | keep
        elif choice == "custom":
            wanted = set(request.POST.getlist("modules")) & set(by_key)
        else:
            messages.error(request, _("Pick an event type."))
            return redirect(_url(event, "modules"))
        result = modules.apply_selection(event, wanted, user=request.user, request=request)
        _save_state(request, event, preset=choice, pending=result["pending"])
        names = {k: str(r["spec"].name) for k, r in by_key.items()}
        if result["on"]:
            messages.success(request, _("Switched on: %(m)s.") % {"m": ", ".join(names[k] for k in result["on"])})
        if result["off"]:
            messages.info(request, _("Switched off: %(m)s.") % {"m": ", ".join(names[k] for k in result["off"])})
        if result["unavailable"]:
            messages.warning(request, _("Not available to you: %(m)s. An instance admin can switch them on for "
                                        "this server.") % {"m": ", ".join(names[k] for k in result["unavailable"])})
        if result["pending"]:
            messages.info(request, _("%(m)s: accept the statement in the next step to switch it on.") % {
                "m": ", ".join(names[k] for k in result["pending"])})
        return _next(request, event, "modules")
    return _render(request, event, "modules", steps, presets=presets, rows=rows,
                   chosen=state.get("preset") or "custom",
                   pending=set(state.get("pending") or []))


def _safety(request, event, steps):
    from apps.accounts import twofactor

    keys = _safety_keys(request, event)
    reg = registry.ensure_loaded().modules
    rows = []
    for key in keys:
        rows.append({"spec": reg[key], "needed": modules.acknowledgement_needed(key, event),
                     "accepted": modules.acknowledgement(key, event), "active": modules.is_enabled(key, event),
                     "can": can_acknowledge(request, event, key),
                     "blocked": modules.blocked_reason(key, request.user)})
    if request.method == "POST":
        todo = [r for r in rows if r["can"] and not r["blocked"] and (r["needed"] or not r["active"])]
        if not all(request.POST.get(f"accept_{r['spec'].key}") == "on" for r in todo if r["needed"]):
            messages.error(request, _("Read the statement and tick the box to switch the module on, or choose "
                                      "“Not now”."))
            return redirect(_url(event, "safety"))
        for r in todo:
            key = r["spec"].key
            modules.acknowledge(event, key, user=request.user, request=request)
            modules.switch_on(event, key, user=request.user, request=request)
            messages.success(request, _("%(m)s is on for this event.") % {"m": r["spec"].name})
        _save_state(request, event, pending=[])
        return _next(request, event, "safety")
    user = request.user
    return _render(request, event, "safety", steps, rows=rows,
                   two_factor={"set_up": user.has_two_factor, "verified": twofactor.is_verified(request)})


def _team(request, event, steps):
    form = forms.InviteForm(request.POST or None, event=event)
    if request.method == "POST":
        if form.is_valid():
            invite_member(request, event, form)
            return redirect(_url(event, "team"))
    members = (Membership.objects.filter(event=event).select_related("user")
               .prefetch_related("assignments__role").order_by("user__email"))
    return _render(request, event, "team", steps, form=form, members=members,
                   invitations=event.invitations.filter(accepted_at__isnull=True, expires_at__gt=timezone.now()),
                   last_invite_url=request.session.pop("evac_last_invite_url", None),
                   next_url=_url(event, next((s for s in STEPS[STEPS.index("team") + 1:] if s in steps), "done")))


def _screens(request, event, steps):
    can_template, can_pair = _can_screens(request, event)
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        if not can_pair:
            raise PermissionDenied("screens.pair")
        if not code:
            messages.error(request, _("Type the code the screen shows."))
            return redirect(_url(event, "screens"))
        return redirect(pair_screen_url(event, code, request.POST.get("name") or "", _url(event, "screens")))
    templates = []
    if can_template:
        templates = sorted((s for s in registry.ensure_loaded().layout_templates.values()
                            if s.module == "core" or modules.is_enabled(s.module, event)),
                           key=lambda s: (s.order, s.name))
    status = {r["key"]: r for r in setup.items(event, request)}
    return _render(request, event, "screens", steps, can_template=can_template, can_pair=can_pair,
                   templates=templates, can_publish=_perm(request, event, "content.publish"),
                   layout_done=bool(status.get("layout", {}).get("done")),
                   screen_done=bool(status.get("screens", {}).get("done")),
                   player_url=request.build_absolute_uri("/player/"), here=_url(event, "screens"),
                   next_url=_url(event, "done"))


def _done(request, event, steps):
    _clear_state(request, event)
    return _render(request, event, "done", steps, checklist=setup.items(event, request),
                   evacuation=modules.is_enabled("evacuation", event))


STEP_VIEWS = {"basics": _basics, "venue": _venue, "modules": _modules, "safety": _safety, "team": _team,
              "screens": _screens, "done": _done}


# --------------------------------------------------------------------------- checklist card

@event_view("events.manage")
def checklist(request, slug, *, event):
    """Hide (or show again) the setup checklist on the overview for this event."""
    if request.method != "POST":
        return redirect("portal:event_dashboard", event.slug)
    setup.set_hidden(event, request.POST.get("hide") == "1", user=request.user, request=request)
    if request.POST.get("hide") == "1":
        messages.info(request, _("Checklist hidden. Show it again under Event settings → Setup checklist."))
    return redirect("portal:event_dashboard", event.slug)
