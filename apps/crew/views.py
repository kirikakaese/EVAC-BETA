# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crew pages: the shift board, a shift with its people and QR code, teams, members, skills; QR check-in and the
staff app's sign-up, check-in and cancel actions."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import services
from .forms import AddPersonForm, MemberForm, ShiftForm, SkillForm, TeamForm
from .models import Assignment, Member, Shift, Skill, Team

MODULE = "crew"


def _fail(request: Any, err: ValidationError) -> None:
    for m in err.messages:
        messages.error(request, m)


def _can_manage(request: Any, event: Any, team: Team | None = None) -> bool:
    if team is not None and services.is_lead(request.user, team):
        return True
    return rbac.has_perm(request.user, event, "crew.manage", obj=team, request=request) if team else \
        rbac.has_any(request.user, event, "crew.manage", request=request)


def _can_checkin(request: Any, event: Any, team: Team) -> bool:
    return _can_manage(request, event, team) or rbac.has_perm(request.user, event, "crew.checkin", obj=team,
                                                              request=request)


def _back(request: Any, default: str) -> Any:
    nxt = request.POST.get("next") or ""
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else default)


# ------------------------------------------------------------------ shift board
@event_view("crew.view", module=MODULE)
def index(request, slug, *, event):
    tz = services._tz(event)
    now = timezone.now()
    days = sorted({s.astimezone(tz).date() for s in Shift.objects.filter(event=event).values_list("starts_at",
                                                                                                 flat=True)})
    today = now.astimezone(tz).date()
    day = parse_date(request.GET.get("day") or "") or (today if today in days or not days else days[0])
    team_id = request.GET.get("team") or ""
    start = dt.datetime.combine(day, dt.time(0), tz)
    shifts = services.window(event, start, start + dt.timedelta(days=1))
    if team_id:
        shifts = shifts.filter(team_id=team_id)
    for s in shifts:
        s.missing = max(0, s.needed - s.filled)
    with timezone.override(tz):
        return render(request, "crew/index.html", {
            "event": event, "days": days, "day": day, "shifts": shifts, "teams": Team.objects.filter(event=event),
            "team_id": team_id, "needed": services.needed_now(event, now), "now": now,
            "can_manage": _can_manage(request, event), "sources": _sources(event)})


def _sources(event: Any) -> list[dict[str, Any]]:
    """Shift sources of the event: extensions with a "shifts" feature (Engelsystem) offer “Sync now” at
    ``<settings page>x/sync/``."""
    from apps.extensions.models import ExtensionConfig

    out = []
    for c in ExtensionConfig.objects.filter(event=event, enabled=True).order_by("extension"):
        spec = c.spec
        if spec is None or not any(f.key == "shifts" for f in spec.features):
            continue
        detail = reverse("extensions:event_detail", args=[event.slug, c.extension])
        out.append({"config": c, "name": spec.name, "detail": detail, "sync": f"{detail}x/sync/"})
    return out


@require_POST
@event_view("crew.manage", module=MODULE)
def install_widgets(request, slug, *, event):
    from apps.core import modules

    from . import presets

    if not modules.is_enabled("widgets", event):
        messages.error(request, _("Switch the widgets module on first."))
        return redirect("crew:index", slug)
    made = presets.install(event, actor=request.user, request=request)
    messages.success(request, _("%(n)s widgets added: put “Crew: needed now” on a layout with a data element.")
                     % {"n": len(made)})
    return redirect("crew:index", slug)


@event_view("crew.view", module=MODULE)
def shift(request, slug, pk, *, event):
    s = get_object_or_404(Shift.objects.select_related("team", "room", "shift_type"), event=event, pk=pk)
    if not rbac.has_perm(request.user, event, "crew.view", obj=s, request=request):
        raise PermissionDenied("crew.view")
    can_manage = _can_manage(request, event, s.team)
    add = AddPersonForm(request.POST if request.POST.get("what") == "add" else None, event=event)
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied("crew.manage")
        if add.is_valid():
            try:
                services.sign_up(s, add.cleaned_data["member"], actor=request.user, request=request,
                                 force=bool(request.POST.get("force")))
            except ValidationError as err:
                _fail(request, err)
                messages.info(request, _("Tick “anyway” to add them all the same."))
            return redirect("crew:shift", slug, s.pk)
    scan_url = request.build_absolute_uri(reverse("crew:scan", args=[slug, s.checkin_token]))
    from apps.accounts.twofactor import qr_svg

    with timezone.override(services._tz(event)):
        return render(request, "crew/shift.html", {
            "event": event, "shift": s, "assignments": s.assignments.select_related("member").order_by("status"),
            "missing": services.missing(s), "can_manage": can_manage,
            "can_checkin": _can_checkin(request, event, s.team), "add": add, "scan_url": scan_url,
            "qr": qr_svg(scan_url), "print": request.GET.get("print") == "1"})


@event_view("crew.view", module=MODULE)
def shift_edit(request, slug, pk=None, *, event):
    s = get_object_or_404(Shift, event=event, pk=pk) if pk else None
    teams = Team.objects.filter(event=event)
    if not _can_manage(request, event, s.team if s else None):
        led = teams.filter(leads=request.user)
        if not led.exists() or (s is not None and s.team not in led):
            raise PermissionDenied("crew.manage")
        teams = led
    with timezone.override(services._tz(event)):
        form = ShiftForm(request.POST or None, instance=s or Shift(event=event), event=event, teams=teams)
        if request.method == "POST" and form.is_valid():
            try:
                obj = services.save_shift(form.save(commit=False), actor=request.user, request=request,
                                          skills=list(form.cleaned_data["skills"]))
            except ValidationError as err:
                _fail(request, err)
            else:
                messages.success(request, _("Shift saved."))
                return redirect("crew:shift", slug, obj.pk)
        return render(request, "crew/shift_form.html", {"event": event, "form": form, "obj": s})


@require_POST
@event_view("crew.view", module=MODULE)
def shift_delete(request, slug, pk, *, event):
    s = get_object_or_404(Shift, event=event, pk=pk)
    if not _can_manage(request, event, s.team):
        raise PermissionDenied("crew.manage")
    services.delete_shift(s, actor=request.user, request=request)
    messages.success(request, _("Shift deleted."))
    return redirect("crew:index", slug)


@require_POST
@event_view("crew.view", module=MODULE)
def assignment(request, slug, pk, *, event):
    """Team lead actions on one person of a shift: check in, check out, no-show, remove."""
    a = get_object_or_404(Assignment.objects.select_related("shift__team", "member"), pk=pk, shift__event=event)
    team = a.shift.team
    action = request.POST.get("action", "")
    if action == "remove" and not _can_manage(request, event, team):
        raise PermissionDenied("crew.manage")
    if not _can_checkin(request, event, team):
        raise PermissionDenied("crew.checkin")
    try:
        if action == "in":
            services.check_in(a, actor=request.user, request=request)
        elif action == "out":
            services.check_out(a, actor=request.user, request=request)
        elif action == "no_show":
            a.status = Assignment.Status.NO_SHOW
            a.save(update_fields=["status"])
            services.changed(event, a.shift)
        elif action == "remove":
            if a.status == Assignment.Status.SIGNED_UP:
                services.cancel(a, actor=request.user, request=request, force=True)
            else:
                a.delete()
                services.changed(event, a.shift)
    except ValidationError as err:
        _fail(request, err)
    return _back(request, reverse("crew:shift", args=[slug, a.shift_id]))


# ------------------------------------------------------------------ QR check-in and the staff app
@event_view("crew.self", module=MODULE)
def scan(request, slug, token, *, event):
    """The shift's QR code: shows the shift; the button checks in (or out)."""
    s = get_object_or_404(Shift.objects.select_related("team", "room"), event=event, checkin_token=token)
    member = services.member_for(request.user, event)
    a = Assignment.objects.filter(shift=s, member=member).first() if member else None
    if request.method == "POST":
        try:
            what, a = services.scan(s, request.user, request=request)
        except ValidationError as err:
            _fail(request, err)
        else:
            messages.success(request, {"in": _("Checked in: %(t)s. Thank you!"), "out": _("Checked out: %(t)s."),
                                       "done": _("You have done %(t)s already.")}[what] % {"t": s.title})
        return redirect("crew:scan", slug, token)
    with timezone.override(services._tz(event)):
        return render(request, "crew/scan.html", {"event": event, "shift": s, "a": a,
                                                  "missing": services.missing(s)})


@require_POST
@event_view("crew.self", module=MODULE)
def sign_up(request, slug, pk, *, event):
    s = get_object_or_404(Shift, event=event, pk=pk)
    if not s.open_signup:
        messages.error(request, _("This shift is filled by the team lead."))
        return _back(request, reverse("portal:staff", args=[slug]))
    member = services.member_for(request.user, event, create=True)
    try:
        services.sign_up(s, member, actor=request.user, request=request, source="self")
    except ValidationError as err:
        _fail(request, err)
    else:
        messages.success(request, _("You are on “%(t)s”.") % {"t": s.title})
    return _back(request, reverse("portal:staff", args=[slug]))


@require_POST
@event_view("crew.self", module=MODULE)
def mine(request, slug, pk, *, event):
    """The staff app's own actions: check in, check out, cancel (offline queue: replays are harmless)."""
    member = services.member_for(request.user, event)
    a = Assignment.objects.select_related("shift").filter(pk=pk, member=member, shift__event=event).first()
    if a is None:
        return _back(request, reverse("portal:staff", args=[slug]))
    action = request.POST.get("action", "")
    try:
        if action == "in" and a.status == Assignment.Status.SIGNED_UP:
            services.check_in(a, actor=request.user, request=request)
        elif action == "out" and a.status == Assignment.Status.CHECKED_IN:
            services.check_out(a, actor=request.user, request=request)
        elif action == "cancel" and a.status == Assignment.Status.SIGNED_UP:
            services.cancel(a, actor=request.user, request=request)
    except ValidationError as err:
        _fail(request, err)
    return _back(request, reverse("portal:staff", args=[slug]))


# ------------------------------------------------------------------ teams, members, skills
@event_view("crew.view", module=MODULE)
def teams(request, slug, *, event):
    can_manage = _can_manage(request, event)
    form = TeamForm(request.POST if request.POST.get("what") == "team" else None, event=event,
                    instance=Team(event=event), prefix="team") if can_manage else None
    skill = SkillForm(request.POST if request.POST.get("what") == "skill" else None, instance=Skill(event=event),
                      prefix="skill") if can_manage else None
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied("crew.manage")
        if form is not None and form.is_bound and form.is_valid():
            services.save_team(form.save(commit=False), actor=request.user, request=request,
                               leads=list(form.cleaned_data["leads"]))
            messages.success(request, _("Team added."))
            return redirect("crew:teams", slug)
        if skill is not None and skill.is_bound and skill.is_valid():
            skill.save()
            messages.success(request, _("Skill added."))
            return redirect("crew:teams", slug)
    from django.db.models import Count

    return render(request, "crew/teams.html", {
        "event": event, "teams": Team.objects.filter(event=event).annotate(n=Count("members", distinct=True))
        .prefetch_related("leads"), "skills": Skill.objects.filter(event=event), "form": form, "skill": skill,
        "can_manage": can_manage, "members": Member.objects.filter(event=event).prefetch_related("teams",
                                                                                                "skills")[:500]})


@event_view("crew.view", module=MODULE)
def member(request, slug, pk=None, *, event):
    m = get_object_or_404(Member, event=event, pk=pk) if pk else Member(event=event)
    if not _can_manage(request, event):
        raise PermissionDenied("crew.manage")
    form = MemberForm(request.POST or None, instance=m, event=event)
    if request.method == "POST" and form.is_valid():
        try:
            services.save_member(form.save(commit=False), actor=request.user, request=request,
                                 teams=list(form.cleaned_data["teams"]), skills=list(form.cleaned_data["skills"]))
        except ValidationError as err:
            _fail(request, err)
        else:
            messages.success(request, _("Saved."))
            return redirect("crew:teams", slug)
    shifts = m.assignments.select_related("shift__team") if pk else []
    return render(request, "crew/member.html", {"event": event, "form": form, "obj": m if pk else None,
                                                "shifts": shifts})
