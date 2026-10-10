# SPDX-License-Identifier: AGPL-3.0-or-later
"""Program pages: the day view with live controls, session editing, stages and tracks; the public page, its exports
and the player data API."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST, require_safe

from apps.core import modules
from apps.events import rbac
from apps.events.models import Event
from apps.portal.shortcuts import event_view

from . import exports, services
from .forms import SessionForm, StageForm, TrackForm
from .models import Session, SessionChange, Stage, Track

MODULE = "program"


def _tz(event: Any) -> Any:
    import zoneinfo

    try:
        return zoneinfo.ZoneInfo(event.timezone or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return dt.UTC


def _days(event: Any) -> list[dt.date]:
    tz = _tz(event)
    days = sorted({s.astimezone(tz).date() for s in Session.objects.filter(event=event).values_list("starts_at",
                                                                                                     flat=True)})
    return days


def _fail(request: Any, err: ValidationError) -> None:
    for msg in err.messages:
        messages.error(request, msg)


def _day_sessions(event: Any, day: dt.date) -> Any:
    tz = _tz(event)
    start = dt.datetime.combine(day, dt.time(0), tz)
    return services.window(event, start, start + dt.timedelta(days=1))


@event_view("program.view", module=MODULE)
def index(request, slug, *, event):
    days = _days(event)
    tz = _tz(event)
    today = timezone.now().astimezone(tz).date()
    day = parse_date(request.GET.get("day") or "") or (today if today in days else (days[0] if days else today))
    stage_id = request.GET.get("stage") or ""
    sessions = _day_sessions(event, day)
    if stage_id:
        sessions = sessions.filter(stage_id=stage_id)
    stages = list(Stage.objects.filter(event=event))
    now = timezone.now()
    on_now = []
    for st in stages:
        cur, nxt = services.now_next(event, st, now)
        if cur or nxt:
            on_now.append({"stage": st, "now": cur, "next": nxt})
    with timezone.override(tz):
        return render(request, "schedule/index.html", {
            "event": event, "days": days, "day": day, "sessions": sessions, "stages": stages, "stage_id": stage_id,
            "on_now": on_now, "now": now, "changes": SessionChange.objects.filter(event=event).select_related(
                "session", "actor")[:12],
            "can_live": rbac.has_any(request.user, event, "program.live", request=request),
            "can_edit": rbac.has_any(request.user, event, "program.edit", request=request),
            "public": services.program_settings(event).get("public_page"), "sources": _sources(event)})


def _sources(event: Any) -> list[dict[str, Any]]:
    """Import sources of the event: extensions with a "sync" feature (pretalx, frab, iCal) offer “Sync now” at
    ``<settings page>x/sync/``."""
    from django.urls import reverse

    from apps.extensions.models import ExtensionConfig

    out = []
    for c in ExtensionConfig.objects.filter(event=event, enabled=True).order_by("extension"):
        spec = c.spec
        if spec is None or not any(f.key == "sync" for f in spec.features):
            continue
        detail = reverse("extensions:event_detail", args=[event.slug, c.extension])
        out.append({"config": c, "name": spec.name, "detail": detail, "sync": f"{detail}x/sync/"})
    return out


@event_view("program.edit", module=MODULE)
def session(request, slug, pk=None, *, event):
    obj = get_object_or_404(Session, event=event, pk=pk) if pk else Session(event=event)
    tz = _tz(event)
    with timezone.override(tz):
        form = SessionForm(request.POST or None, instance=obj, event=event)
        if request.method == "POST" and form.is_valid():
            s = form.save(commit=False)
            try:
                services.save_session(s, actor=request.user, request=request, speakers=form.speakers(),
                                      changed=["speakers" if f == "speakers_text" else f
                                                                     for f in form.changed_data])
            except ValidationError as err:
                _fail(request, err)
            else:
                messages.success(request, _("Session saved."))
                return redirect("schedule:index", slug)
        return render(request, "schedule/session.html", {"event": event, "form": form, "obj": obj,
                                                         "is_saved": bool(pk)})


@require_POST
@event_view("program.edit", module=MODULE)
def session_delete(request, slug, pk, *, event):
    s = get_object_or_404(Session, event=event, pk=pk)
    services.delete_session(s, actor=request.user, request=request)
    messages.success(request, _("Session deleted."))
    return redirect("schedule:index", slug)


@require_POST
@event_view("program.live", module=MODULE)
def live(request, slug, pk, *, event):
    """One live action from the day view: delay, cancel, move, restore, reset (back to the source)."""
    s = get_object_or_404(Session.objects.select_related("stage"), event=event, pk=pk)
    action = request.POST.get("action", "")
    note = request.POST.get("note")
    note = note.strip() if note is not None and note.strip() else None
    try:
        if action == "delay":
            services.delay(s, int(request.POST.get("minutes") or 0), actor=request.user, request=request, note=note,
                           shift_following=bool(request.POST.get("following")))
        elif action == "cancel":
            services.cancel(s, actor=request.user, request=request, note=note)
        elif action == "move":
            target = request.POST.get("stage") or ""
            stage = get_object_or_404(Stage, event=event, pk=target) if target else None
            services.move(s, stage, actor=request.user, request=request, note=note)
        elif action == "restore":
            services.restore(s, actor=request.user, request=request)
        elif action == "reset":
            if not rbac.has_any(request.user, event, "program.edit", request=request):
                raise PermissionDenied("program.edit")
            services.reset_overrides(s, actor=request.user, request=request)
        else:
            raise ValidationError(_("Unknown action."))
    except ValueError:
        messages.error(request, _("Give the delay in minutes."))
    except ValidationError as err:
        _fail(request, err)
    else:
        messages.success(request, _("Done: screens and the public program show the change."))
    day = timezone.localtime(s.starts_at, _tz(event)).date().isoformat()
    from django.urls import reverse

    return redirect(f"{reverse('schedule:index', args=[slug])}?day={day}")


@event_view("program.edit", module=MODULE)
def stages(request, slug, *, event):
    stage_form = StageForm(request.POST if request.POST.get("what") == "stage" else None,
                           instance=Stage(event=event), event=event, prefix="stage")
    track_form = TrackForm(request.POST if request.POST.get("what") == "track" else None,
                           instance=Track(event=event), prefix="track")
    for form, label in ((stage_form, "stage"), (track_form, "track")):
        if form.is_bound and form.is_valid():
            obj = form.save()
            from apps.core.audit import log

            log(action=f"program.{label}_created", actor=request.user, target=obj, event=event, request=request,
                message=f"{label.title()} {obj.name}")
            messages.success(request, _("Saved."))
            return redirect("schedule:stages", slug)
    return render(request, "schedule/stages.html", {
        "event": event, "stage_form": stage_form, "track_form": track_form,
        "stages": Stage.objects.filter(event=event).select_related("room"),
        "tracks": Track.objects.filter(event=event)})


@require_POST
@event_view("program.edit", module=MODULE)
def stage_delete(request, slug, pk, *, event):
    st = get_object_or_404(Stage, event=event, pk=pk)
    from apps.core.audit import log

    log(action="program.stage_deleted", actor=request.user, target=st, event=event, request=request,
        message=f"Stage {st.name} deleted")
    st.delete()
    services.notify(event)
    return redirect("schedule:stages", slug)


# ------------------------------------------------------------------ public
def _public_event(slug: str) -> Event:
    event = get_object_or_404(Event, slug=slug)
    if not modules.is_enabled(MODULE, event) or not services.program_settings(event).get("public_page"):
        raise Http404
    return event


@require_safe
def public(request, slug):
    event = _public_event(slug)
    tz = _tz(event)
    days: dict[dt.date, list[Session]] = {}
    for s in exports.sessions(event):
        days.setdefault(s.starts_at.astimezone(tz).date(), []).append(s)
    with timezone.override(tz):
        resp = render(request, "schedule/public.html", {"event": event, "days": sorted(days.items()),
                                                        "now": timezone.now()})
    resp["Cache-Control"] = "public, max-age=30"
    return resp


@require_safe
def public_ics(request, slug):
    event = _public_event(slug)
    resp = HttpResponse(exports.ical(event, request.get_host().split(":")[0]), content_type="text/calendar; "
                        "charset=utf-8")
    resp["Content-Disposition"] = f'inline; filename="{event.slug}-program.ics"'
    resp["Cache-Control"] = "public, max-age=60"
    return resp


@require_safe
def public_json(request, slug):
    resp = JsonResponse(exports.as_json(_public_event(slug)))
    resp["Cache-Control"] = "public, max-age=60"
    return resp


@require_safe
def public_frab(request, slug):
    resp = HttpResponse(exports.frab(_public_event(slug)), content_type="application/xml; charset=utf-8")
    resp["Cache-Control"] = "public, max-age=60"
    return resp


# ------------------------------------------------------------------ player
@require_safe
def player_data(request):
    """``/player/api/schedule/`` (screen token): sessions around now, stages and recent changes. The player keeps
    the answer for offline use and computes now/next itself; ``schedule.changed`` makes it ask again."""
    from apps.screens.player_api import _screen, _unauthorized

    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    if not modules.is_enabled(MODULE, screen.event):
        return JsonResponse({"sessions": [], "stages": [], "changes": []})
    data = services.screen_payload(screen.event)
    data["screen_room"] = str(screen.room_id) if screen.room_id else None
    return JsonResponse(data)
