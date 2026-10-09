# SPDX-License-Identifier: AGPL-3.0-or-later
"""Playback pages: what screens show now, playlists, schedules with calendar, live overrides and the preview."""
from __future__ import annotations

import datetime as dt
from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.content import files as content_files
from apps.content import services as content_services
from apps.content import tokens as tok
from apps.content.layout_views import editor_version
from apps.content.models import Asset, Layout, owner_q
from apps.core import modules
from apps.events import rbac
from apps.portal.shortcuts import event_view
from apps.screens.models import Screen
from apps.screens.views import _with_health

from . import forms, services
from .models import Override, Playlist, PlaylistItem, ScheduleRule

SOURCE_LABEL = {"override": _("Override"), "schedule": _("Schedule"), "default": _("Default"),
                "nothing": _("Nothing")}


def playback_view(perm: str, module: str = "playlists"):
    """``event_view`` plus the event's time zone for forms and dates on these pages."""
    def deco(fn):
        @event_view(perm, module=module)
        @wraps(fn)
        def wrapper(request, slug, *args, event, **kwargs):
            with timezone.override(services._tz(event)):
                return fn(request, slug, *args, event=event, **kwargs)
        return wrapper
    return deco


def _render(request, template, ctx):
    event = ctx["event"]
    ctx.setdefault("schedules_on", modules.is_enabled("schedules", event))
    ctx.setdefault("overrides_on", modules.is_enabled("overrides", event))
    return render(request, template, ctx)


def _perm(request, event, perm, obj=None) -> bool:
    return rbac.has_perm(request.user, event, perm, obj=obj, request=request)


def _fail(request, err: ValidationError) -> None:
    for m in err.messages:
        messages.error(request, m)


def _from_ms(ms):
    return None if ms is None else dt.datetime.fromtimestamp(ms / 1000, tz=dt.UTC)


def _label(found, layouts: dict, event) -> dict:
    """Human readable 'what is on' for templates."""
    if found is None or found.get("source") == "nothing":
        return {**(found or {}), "source": "nothing", "source_label": SOURCE_LABEL["nothing"],
                "what": _("nothing (idle screen)")}
    if "message" in found:
        what = _("Message")
    else:
        what = layouts.get(found.get("layout"), "?")
    return {**found, "source_label": SOURCE_LABEL.get(found["source"], found["source"]), "what": what,
            "until": _from_ms(found.get("end"))}


def _layout_names(event) -> dict[str, str]:
    return {str(pk): name for pk, name in Layout.objects.filter(event=event).values_list("pk", "name")}


# ------------------------------------------------------------------ dashboard
@playback_view("playlists.view")
def index(request, slug, *, event):
    names = _layout_names(event)
    now = timezone.now()
    screens = []
    paired = Screen.objects.paired().filter(event=event).select_related("venue", "zone", "room")
    for screen in _with_health(event, list(paired)):
        screens.append({"screen": screen, "on": _label(services.now_playing(screen, now), names, event)})
    overrides = (Override.objects.current(now).filter(event=event).select_related("layout", "playlist", "created_by")
                 .prefetch_related("groups", "screens")) if modules.is_enabled("overrides", event) else []
    return _render(request, "playlists/index.html", {
        "event": event, "screens": screens, "overrides": overrides,
        "playlists": Playlist.objects.filter(event=event).prefetch_related("items"),
        "can_override": rbac.has_any(request.user, event, "playlists.override", request=request),
        "now": now,
    })


# ------------------------------------------------------------------ playlists
@playback_view("playlists.view")
def playlists(request, slug, *, event):
    can_edit = _perm(request, event, "playlists.edit")
    form = forms.PlaylistForm(request.POST or None, event=event, prefix="new") if can_edit else None
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            pl = form.save(commit=False)
            pl.event = event
            services.save_playlist(pl, actor=request.user, request=request)
            messages.success(request, _("Playlist created. Add layouts to it."))
            return redirect("playlists:playlist", slug, pl.pk)
    return _render(request, "playlists/playlists.html", {
        "event": event, "form": form,
        "playlists": Playlist.objects.filter(event=event).prefetch_related("items"),
    })


@playback_view("playlists.view")
def playlist(request, slug, pk, *, event):
    pl = get_object_or_404(Playlist, event=event, pk=pk)
    can_edit = _perm(request, event, "playlists.edit")
    meta = forms.PlaylistForm(request.POST or None, instance=pl, event=event, prefix="meta") if can_edit else None
    add = forms.ItemForm(request.POST or None, playlist=pl, prefix="add") if can_edit else None
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        action = request.POST.get("action")
        try:
            if action == "add":
                add = forms.ItemForm(request.POST, playlist=pl, prefix="add")
                if add.is_valid():
                    services.save_item(add.save(commit=False), actor=request.user, request=request)
                    messages.success(request, _("Added."))
                    return redirect("playlists:playlist", slug, pl.pk)
                meta = forms.PlaylistForm(instance=pl, event=event, prefix="meta")
            elif action in ("up", "down", "remove", "toggle"):
                item = get_object_or_404(PlaylistItem, playlist=pl, pk=request.POST.get("item"))
                if action == "remove":
                    services.delete_item(item, actor=request.user, request=request)
                elif action == "toggle":
                    item.enabled = not item.enabled
                    services.save_item(item, actor=request.user, request=request)
                else:
                    services.move_item(item, -1 if action == "up" else 1, actor=request.user, request=request)
                return redirect("playlists:playlist", slug, pl.pk)
            elif action == "delete":
                services.delete_playlist(pl, actor=request.user, request=request)
                messages.success(request, _("Playlist deleted."))
                return redirect("playlists:playlists", slug)
            else:
                add = forms.ItemForm(playlist=pl, prefix="add")
                if meta.is_valid():
                    services.save_playlist(meta.save(commit=False), actor=request.user, request=request)
                    messages.success(request, _("Saved."))
                    return redirect("playlists:playlist", slug, pl.pk)
        except ValidationError as err:
            _fail(request, err)
            return redirect("playlists:playlist", slug, pl.pk)
    items = list(pl.items.select_related("layout__published", "child"))
    total = 0
    for item in items:
        if item.layout_id:
            own = (item.layout.published.data.get("duration") if item.layout.published_id else None)
            item.seconds = item.duration or own or pl.default_duration
            item.live = item.layout.published_id is not None
        else:
            item.seconds = None
            item.live = True
        if item.enabled and item.seconds:
            total += item.seconds * (item.weight if pl.mode == Playlist.Mode.WEIGHTED else 1)
    return _render(request, "playlists/playlist.html", {
        "event": event, "playlist": pl, "items": items, "meta": meta, "add": add, "can_edit": can_edit,
        "total": total, "used_by": ScheduleRule.objects.filter(playlist=pl),
    })


# ------------------------------------------------------------------ schedules
@playback_view("playlists.view", module="schedules")
def schedules(request, slug, *, event):
    can_edit = _perm(request, event, "playlists.edit")
    return _render(request, "playlists/schedules.html", {
        "event": event, "can_edit": can_edit,
        "rules": ScheduleRule.objects.filter(event=event).select_related("layout", "playlist")
        .prefetch_related("groups", "screens"),
        "weekday_names": dict(forms.WEEKDAYS),
    })


@playback_view("playlists.edit", module="schedules")
def schedule(request, slug, pk=None, *, event):
    rule = get_object_or_404(ScheduleRule, event=event, pk=pk) if pk else ScheduleRule(event=event)
    form = forms.ScheduleForm(request.POST or None, instance=rule, event=event)
    if request.method == "POST":
        if request.POST.get("action") == "delete" and pk:
            services.delete_rule(rule, actor=request.user, request=request)
            messages.success(request, _("Schedule deleted."))
            return redirect("playlists:schedules", slug)
        if form.is_valid():
            obj = form.save(commit=False)
            try:
                services.save_rule(obj, actor=request.user, request=request,
                                   m2m={"groups": form.cleaned_data["groups"],
                                        "screens": form.cleaned_data["screens"]})
            except ValidationError as err:
                _fail(request, err)
            else:
                messages.success(request, _("Schedule saved."))
                return redirect("playlists:schedules", slug)
    return _render(request, "playlists/schedule.html", {"event": event, "form": form, "rule": rule if pk else None})


@playback_view("playlists.view", module="schedules")
def calendar(request, slug, *, event):
    form = forms.CalendarForm(request.GET or None, event=event)
    group, week = None, None
    if form.is_valid():
        group, week = form.cleaned_data["group"], form.cleaned_data["week"]
    tz = services._tz(event)
    today = timezone.now().astimezone(tz).date()
    week = week or today
    monday = week - dt.timedelta(days=week.weekday())
    start = dt.datetime.combine(monday, dt.time(0), tzinfo=tz)
    target = services.Target(group=group)
    program = services.build_program(event, target, now=timezone.now(), start=start, days=7)
    ctx = target.context(event)
    days, blocks, legend = [], [], {}
    palette = 8
    for n in range(7):
        day = monday + dt.timedelta(days=n)
        d0 = dt.datetime.combine(day, dt.time(0), tzinfo=tz)
        d1 = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0), tzinfo=tz)
        days.append({"date": day, "today": day == today})
        for seg in services.segments(program, ctx, services._ms(d0), services._ms(d1)):
            if seg["entry"] is None:
                continue
            key = seg["entry"]
            legend.setdefault(key, {"name": seg["name"], "source": SOURCE_LABEL.get(seg["source"]),
                                    "colour": len(legend) % palette})
            # quarter-hour rows: 96 per day (+1 for the CSS grid line numbers)
            a = round((seg["from"] - services._ms(d0)) / 900000)
            b = max(a + 1, round((seg["to"] - services._ms(d0)) / 900000))
            blocks.append({"id": f"b{len(blocks)}", "col": n + 2, "row_from": a + 2, "row_to": b + 2,
                           "name": seg["name"], "colour": legend[key]["colour"], "source": seg["source"],
                           "from": _from_ms(seg["from"]), "to": _from_ms(seg["to"])})
    return _render(request, "playlists/calendar.html", {
        "event": event, "form": form, "days": days, "blocks": blocks, "legend": legend.values(),
        "hours": [(h, h * 4 + 2) for h in range(24)], "prev": monday - dt.timedelta(days=7),
        "next": monday + dt.timedelta(days=7), "group": group, "monday": monday,
    })


# ------------------------------------------------------------------ overrides
@playback_view("playlists.view", module="overrides")
def overrides(request, slug, *, event):
    can_push = rbac.has_any(request.user, event, "playlists.override", request=request)
    allow_emergency = rbac.has_any(request.user, event, "playlists.emergency", request=request)
    form = (forms.OverrideForm(request.POST or None, event=event, allow_emergency=allow_emergency,
                               initial={"all_screens": True}) if can_push else None)
    if request.method == "POST":
        if not can_push:
            raise PermissionDenied
        if form.is_valid():
            cd = form.cleaned_data
            perm = "playlists.emergency" if cd["level"] == Override.Level.EMERGENCY else "playlists.override"
            if not services.may_target(request.user, event, perm, all_screens=cd["all_screens"],
                                       groups=cd["groups"], screens=cd["screens"], request=request):
                form.add_error(None, _("You may not push this to all of the chosen screens."))
            else:
                ov = form.save(commit=False)
                ov.starts_at, ov.expires_at = cd["starts_at"], cd["expires_at"]
                try:
                    services.push_override(ov, actor=request.user, request=request,
                                           m2m={"groups": cd["groups"], "screens": cd["screens"]})
                except ValidationError as err:
                    _fail(request, err)
                else:
                    messages.success(request, _("Override pushed to the screens."))
                    return redirect("playlists:overrides", slug)
    now = timezone.now()
    current = list(Override.objects.current(now).filter(event=event).select_related("layout", "playlist",
                                                                                     "created_by")
                   .prefetch_related("groups", "screens"))
    history = (Override.objects.filter(event=event).exclude(pk__in=[o.pk for o in current])
               .select_related("layout", "playlist", "created_by", "cancelled_by")
               .prefetch_related("groups", "screens")[:30])
    return _render(request, "playlists/overrides.html", {
        "event": event, "form": form, "current": current, "history": history, "now": now,
    })


@require_POST
@playback_view("playlists.view", module="overrides")
def override_cancel(request, slug, pk, *, event):
    ov = get_object_or_404(Override.objects.prefetch_related("groups", "screens"), event=event, pk=pk)
    perm = "playlists.emergency" if ov.level == Override.Level.EMERGENCY else "playlists.override"
    if not services.may_target(request.user, event, perm, all_screens=ov.all_screens, groups=ov.groups.all(),
                               screens=ov.screens.all(), request=request):
        raise PermissionDenied
    services.cancel_override(ov, actor=request.user, request=request)
    messages.success(request, _("Override cancelled."))
    nxt = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect("playlists:overrides", slug)


# ------------------------------------------------------------------ preview
@playback_view("playlists.view")
def preview(request, slug, *, event):
    form = forms.PreviewForm(request.GET or None, event=event)
    ctx = {"event": event, "form": form, "editor_version": editor_version()}
    if form.is_valid():
        screen = form.cleaned_data["screen"]
        at = form.cleaned_data["at"] or timezone.now()
        target = services.Target(screen=screen)
        program = services.build_program(event, target, now=at, days=1)
        vars_ = target.context(event)
        t = services._ms(at)
        names = _layout_names(event)
        found = services.describe(program, vars_, t)
        steps = []
        for entry, window in services.engine.candidates(program, t):
            steps.append({"entry": entry, "source_label": SOURCE_LABEL.get(entry["source"]),
                          "wins": found is not None and found["entry"] == entry["id"],
                          "until": _from_ms(window[1])})
        timeline = [_label(s, names, event) | {"from_dt": _from_ms(s["from"]), "to_dt": _from_ms(s["to"])}
                    for s in services.timeline(program, vars_, t, t + 2 * 3600 * 1000, limit=12)]
        segments = [{**seg, "from_dt": _from_ms(seg["from"]), "to_dt": _from_ms(seg["to"])}
                    for seg in services.segments(program, vars_, t, t + 24 * 3600 * 1000)]
        ctx.update(screen=screen, at=at, now_on=_label(found, names, event), steps=steps, timeline=timeline,
                   segments=segments,
                   config=_preview_config(event, program, found, vars_, t))
    return _render(request, "playlists/preview.html", ctx)


def _preview_config(event, program, found, vars_, t) -> dict | None:
    """Data for the preview island (renders the slide with the shared renderer at that time)."""
    if found is None:
        return None
    if "message" in found:
        data, theme = program["messages"][found["message"]], None
    else:
        lay = Layout.objects.select_related("published", "theme").filter(event=event, pk=found["layout"]).first()
        if lay is None or not lay.published_id:
            return None
        data, theme = lay.published.data, lay.theme
    theme = theme or content_services.event_theme(event)
    values = content_services.resolved_tokens(theme)
    assets = Asset.objects.filter(owner_q(event), status=Asset.Status.READY)
    images = {str(a.pk): content_files.asset_url(a, a.variant("webp", "original"))
              for a in assets if str(a.pk) in tok.referenced_assets(values)}
    return {"layout": data, "at": t, "timezone": event.timezone, "vars": vars_,
            "assets": {str(a.pk): content_services.asset_entry(a, content_files.portal_url) for a in assets},
            "fonts": content_services.font_stacks(event),
            "themeVariables": tok.css_variables(values, families=content_services.font_stacks(event), urls=images)}

