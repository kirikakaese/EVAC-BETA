# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crew services (ADR-0041): sign-up with rules, check-in/out (also by QR), no-shows, "needed now".

Rules for signing up (settings namespace ``crew``): the shift is open and not full, has not started (or started
less than ``late_signup_minutes`` ago), the member has the skills it needs, no other shift of theirs overlaps, a
rest of ``min_rest_minutes`` lies between shifts and their shifts of that day add up to at most
``max_hours_per_day``. Team leads and ``crew.manage`` can sign people up anyway (``force``); that is audited.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import modules, settings_store, webhooks
from apps.core.audit import log

from .models import Assignment, Member, Shift, Team

MODULE = "crew"
FEEDS = ("crew.needed_now", "crew.board")


def crew_settings(event: Any) -> dict[str, Any]:
    return settings_store.get("crew", event=event)


def _user(actor: Any) -> Any:
    return actor if getattr(actor, "pk", None) and getattr(actor, "is_authenticated", True) else None


def _tz(event: Any) -> Any:
    import zoneinfo

    try:
        return zoneinfo.ZoneInfo(event.timezone or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return dt.UTC


def member_for(user: Any, event: Any, *, create: bool = False) -> Member | None:
    if not getattr(user, "is_authenticated", False):
        return None
    m = Member.objects.filter(event=event, user=user).first()
    if m is None and create:
        m, _created = Member.objects.get_or_create(event=event, user=user, defaults={
            "name": (getattr(user, "display_name", "") or user.email)[:120]})
    return m


def is_lead(user: Any, team: Team) -> bool:
    return bool(getattr(user, "pk", None)) and team.leads.filter(pk=user.pk).exists()


def changed(event: Any, shift: Shift | None = None) -> None:
    """After the commit: the shift board on screens and integrations follow."""
    def run() -> None:
        if shift is not None:
            webhooks.emit("crew.shift_changed", payload_of(shift), event=event)
        refresh_feeds(event)
    transaction.on_commit(run)


def refresh_feeds(event: Any) -> int:
    """Fetch the event's crew feeds now so screens see sign-ups and check-ins at once."""
    from django.apps import apps

    if not apps.is_installed("apps.widgets") or not modules.is_enabled("widgets", event):
        return 0
    from apps.widgets import services as widgets
    from apps.widgets.models import Feed

    n = 0
    for feed in Feed.objects.filter(event=event, kind=Feed.Kind.SOURCE, source__in=FEEDS, enabled=True):
        widgets.fetch_feed(feed)
        n += 1
    return n


def payload_of(shift: Shift) -> dict[str, Any]:
    active = shift.assignments.filter(status__in=Assignment.ACTIVE).count()
    return {"id": str(shift.pk), "event": shift.event.slug, "team": shift.team.name, "title": shift.title,
            "starts_at": shift.starts_at.isoformat(), "ends_at": shift.ends_at.isoformat(), "place": shift.place,
            "needed": shift.needed, "filled": active, "missing": max(0, shift.needed - active)}


# ------------------------------------------------------------------ editing
def save_team(team: Team, *, actor: Any, request: Any = None, leads: list[Any] | None = None) -> Team:
    if not team.name.strip():
        raise ValidationError(_("Give the team a name."))
    created = team._state.adding
    team.save()
    if leads is not None:
        team.leads.set(leads)
    log(action="crew.team_created" if created else "crew.team_edited", actor=actor, target=team, event=team.event,
        request=request, message=team.name)
    return team


def save_member(m: Member, *, actor: Any, request: Any = None, teams: list[Any] | None = None,
                skills: list[Any] | None = None) -> Member:
    if not m.name.strip():
        raise ValidationError(_("Give a name."))
    created = m._state.adding
    m.save()
    if teams is not None:
        m.teams.set(teams)
    if skills is not None:
        m.skills.set(skills)
    log(action="crew.member_added" if created else "crew.member_edited", actor=actor, target=m, event=m.event,
        request=request, message=m.name)
    return m


def save_shift(s: Shift, *, actor: Any, request: Any = None, skills: list[Any] | None = None) -> Shift:
    if not s.title.strip():
        raise ValidationError(_("Give the shift a title."))
    if s.ends_at <= s.starts_at:
        raise ValidationError(_("The end must be after the start."))
    if s.team.event_id != s.event_id:
        raise ValidationError(_("The team belongs to another event."))
    created = s._state.adding
    s.save()
    if skills is not None:
        s.skills.set(skills)
    log(action="crew.shift_created" if created else "crew.shift_edited", actor=actor, target=s, event=s.event,
        request=request, message=f"{s.team.name}: {s.title}")
    changed(s.event, s)
    return s


def delete_shift(s: Shift, *, actor: Any, request: Any = None) -> None:
    event = s.event
    log(action="crew.shift_deleted", actor=actor, target=s, event=event, request=request,
        message=f"{s.team.name}: {s.title}")
    s.delete()
    changed(event)


# ------------------------------------------------------------------ rules
def problems(shift: Shift, member: Member, now: dt.datetime | None = None) -> list[str]:
    """Why ``member`` may not sign up for ``shift`` (empty: may)."""
    now = now or timezone.now()
    cfg = crew_settings(shift.event)
    out = []
    active = shift.assignments.filter(status__in=Assignment.ACTIVE).exclude(member=member).count()
    if active >= shift.needed:
        out.append(_("The shift is full."))
    late = dt.timedelta(minutes=int(cfg.get("late_signup_minutes", 30)))
    if shift.starts_at + late < now:
        out.append(_("The shift has already started."))
    missing = set(shift.skills.values_list("name", flat=True)) - set(member.skills.values_list("name", flat=True))
    if missing:
        out.append(_("Skills needed: %(s)s.") % {"s": ", ".join(sorted(missing))})
    mine = list(Shift.objects.filter(assignments__member=member, assignments__status__in=Assignment.ACTIVE)
                .exclude(pk=shift.pk))
    rest = dt.timedelta(minutes=int(cfg.get("min_rest_minutes", 30)))
    for other in mine:
        if other.starts_at < shift.ends_at and shift.starts_at < other.ends_at:
            out.append(_("It overlaps with “%(t)s”.") % {"t": other.title})
        elif other.ends_at <= shift.starts_at < other.ends_at + rest or \
                shift.ends_at <= other.starts_at < shift.ends_at + rest:
            out.append(_("Less than %(m)s minutes rest after or before “%(t)s”.") % {
                "m": int(rest.total_seconds() // 60), "t": other.title})
    tz = _tz(shift.event)
    day = shift.starts_at.astimezone(tz).date()
    hours = shift.hours + sum(o.hours for o in mine if o.starts_at.astimezone(tz).date() == day)
    limit = float(cfg.get("max_hours_per_day", 10))
    if hours > limit:
        out.append(_("That makes %(h)s hours on that day (at most %(m)s).") % {"h": f"{hours:g}", "m": f"{limit:g}"})
    return out


def sign_up(shift: Shift, member: Member, *, actor: Any, request: Any = None, force: bool = False,
            source: str = "") -> Assignment:
    if member.event_id != shift.event_id:
        raise ValidationError(_("The member belongs to another event."))
    with transaction.atomic():
        locked = Shift.objects.select_for_update().get(pk=shift.pk)
        old = Assignment.objects.filter(shift=locked, member=member).first()
        if old is not None and old.status in Assignment.ACTIVE:
            return old
        issues = problems(locked, member)
        if issues and not force:
            raise ValidationError(issues)
        if old is not None:  # a no-show signs up again
            old.status, old.by, old.checked_in_at, old.checked_out_at = Assignment.Status.SIGNED_UP, _user(actor), \
                None, None
            old.save()
            a = old
        else:
            try:
                a = Assignment.objects.create(shift=locked, member=member, by=_user(actor), source=source)
            except IntegrityError:
                return Assignment.objects.get(shift=locked, member=member)
    log(action="crew.signed_up" + ("_forced" if issues and force else ""), actor=actor, target=a,
        event=shift.event, request=request, message=f"{member.name} → {shift.team.name}: {shift.title}",
        changes={"problems": issues} if issues else None)
    changed(shift.event, shift)
    return a


def cancel(a: Assignment, *, actor: Any, request: Any = None, force: bool = False) -> None:
    shift = a.shift
    if a.status != Assignment.Status.SIGNED_UP:
        raise ValidationError(_("Only a sign-up that has not started can be cancelled."))
    cfg = crew_settings(shift.event)
    if not force and shift.starts_at - timezone.now() < dt.timedelta(minutes=int(cfg.get("cancel_until_minutes",
                                                                                          60))):
        raise ValidationError(_("Too close to the start: ask your team lead."))
    log(action="crew.cancelled", actor=actor, target=a, event=shift.event, request=request,
        message=f"{a.member.name} ✕ {shift.team.name}: {shift.title}")
    a.delete()
    changed(shift.event, shift)


def check_in(a: Assignment, *, actor: Any, request: Any = None, at: dt.datetime | None = None) -> Assignment:
    if a.status == Assignment.Status.CHECKED_IN:
        return a
    a.status, a.checked_in_at = Assignment.Status.CHECKED_IN, at or timezone.now()
    a.save(update_fields=["status", "checked_in_at"])
    if not a.member.arrived:
        Member.objects.filter(pk=a.member_id).update(arrived=True)
    log(action="crew.checked_in", actor=actor, target=a, event=a.shift.event, request=request,
        message=f"{a.member.name}: {a.shift.title}")
    changed(a.shift.event, a.shift)
    return a


def check_out(a: Assignment, *, actor: Any, request: Any = None, at: dt.datetime | None = None) -> Assignment:
    if a.status != Assignment.Status.CHECKED_IN:
        raise ValidationError(_("Not checked in."))
    a.status, a.checked_out_at = Assignment.Status.DONE, at or timezone.now()
    a.save(update_fields=["status", "checked_out_at"])
    log(action="crew.checked_out", actor=actor, target=a, event=a.shift.event, request=request,
        message=f"{a.member.name}: {a.shift.title}")
    changed(a.shift.event, a.shift)
    return a


def scan(shift: Shift, user: Any, *, request: Any = None) -> tuple[str, Assignment]:
    """The shift's QR code was scanned by ``user``: check in, or out when already in. A member who is not signed up
    joins the shift when it still needs people ("walk-in"). Returns ``(what happened, assignment)``."""
    member = member_for(user, shift.event, create=True)
    a = Assignment.objects.filter(shift=shift, member=member).first()
    if a is None or a.status == Assignment.Status.NO_SHOW:
        a = sign_up(shift, member, actor=user, request=request, source="qr")
    if a.status == Assignment.Status.SIGNED_UP:
        return "in", check_in(a, actor=user, request=request)
    if a.status == Assignment.Status.CHECKED_IN:
        return "out", check_out(a, actor=user, request=request)
    return "done", a


def mark_no_shows(now: dt.datetime | None = None) -> int:
    """Beat task: sign-ups not checked in ``no_show_minutes`` after the start become no-shows; team leads hear
    about it and the shift shows up as "needed now" again."""
    from apps.core.notify import notify

    now = now or timezone.now()
    n = 0
    for a in (Assignment.objects.filter(status=Assignment.Status.SIGNED_UP, shift__starts_at__lt=now,
                                        shift__ends_at__gt=now - dt.timedelta(hours=1))
              .select_related("shift__event", "shift__team", "member")):
        event = a.shift.event
        if not modules.is_enabled(MODULE, event):
            continue
        if a.shift.starts_at + dt.timedelta(minutes=int(crew_settings(event).get("no_show_minutes", 15))) > now:
            continue
        a.status = Assignment.Status.NO_SHOW
        a.save(update_fields=["status"])
        n += 1
        log(action="crew.no_show", target=a, event=event, message=f"{a.member.name}: {a.shift.title}")
        notify(list(a.shift.team.leads.all()), _("No-show: %(m)s (%(t)s)") % {"m": a.member.name,
                                                                              "t": a.shift.title},
               body=_("The shift needs %(n)s more.") % {"n": missing(a.shift)}, level="warn", event=event,
               url=f"/e/{event.slug}/crew/shifts/{a.shift.pk}/")
        webhooks.emit("crew.no_show", {**payload_of(a.shift), "member": a.member.name}, event=event)
        refresh_feeds(event)
    return n


# ------------------------------------------------------------------ reading
def missing(shift: Shift) -> int:
    return max(0, shift.needed - shift.assignments.filter(status__in=Assignment.ACTIVE).count())


def window(event: Any, start: dt.datetime, end: dt.datetime) -> Any:
    return (Shift.objects.filter(event=event, ends_at__gt=start, starts_at__lt=end)
            .select_related("team", "room").annotate(
                filled=Count("assignments", filter=Q(assignments__status__in=Assignment.ACTIVE)),
                present=Count("assignments", filter=Q(assignments__status=Assignment.Status.CHECKED_IN)))
            .order_by("starts_at", "team__name", "title"))


def needed_now(event: Any, now: dt.datetime | None = None, *, hours: float | None = None) -> list[dict[str, Any]]:
    """Shifts running now or starting within ``hours`` that still need people (the "needed now" board)."""
    now = now or timezone.now()
    hours = float(hours if hours is not None else crew_settings(event).get("needed_now_hours", 3))
    tz = _tz(event)
    out = []
    for s in window(event, now, now + dt.timedelta(hours=hours)):
        gap = s.needed - s.filled
        if gap <= 0:
            continue
        out.append({"id": str(s.pk), "team": s.team.name, "colour": s.team.colour, "title": s.title,
                    "place": s.place, "start": s.starts_at.isoformat(), "end": s.ends_at.isoformat(),
                    "time": f"{s.starts_at.astimezone(tz):%H:%M}–{s.ends_at.astimezone(tz):%H:%M}",
                    "missing": gap, "needed": s.needed, "now": s.starts_at <= now,
                    "need": _("%(n)s needed") % {"n": gap},
                    "label": _("now") if s.starts_at <= now else _("from %(t)s") % {
                        "t": f"{s.starts_at.astimezone(tz):%H:%M}"}})
    return sorted(out, key=lambda r: (not r["now"], r["start"], -r["missing"]))
