# SPDX-License-Identifier: AGPL-3.0-or-later
"""Playlists, schedules and overrides: state changes (audit-logged) and the per-screen **program**."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import modules, webhooks
from apps.core.audit import log
from apps.core.registry import registry

from . import engine
from .models import PRIORITY_DEFAULT, Override, Playlist, PlaylistItem, ScheduleRule

HORIZON_DAYS = 7


def _ms(value: dt.datetime | None) -> int | None:
    return None if value is None else int(value.timestamp() * 1000)


def _tz(event) -> ZoneInfo:
    try:
        return ZoneInfo(event.timezone or "UTC")
    except Exception:  # noqa: BLE001 - unknown zone name
        return ZoneInfo("UTC")


# ------------------------------------------------------------------ targets
class Target:
    """Who is asking: a screen (its id and groups) or a whole screen group (calendar)."""

    def __init__(self, *, screen=None, group=None):
        self.screen = screen
        self.group = group
        if screen is not None:
            self.group_ids = {g.pk for g in screen.groups()}
        else:
            self.group_ids = {group.pk} if group is not None else set()

    def matches(self, obj) -> bool:
        if obj.all_screens:
            return True
        if any(g.pk in self.group_ids for g in obj.groups.all()):
            return True
        return self.screen is not None and any(s.pk == self.screen.pk for s in obj.screens.all())

    def context(self, event) -> dict[str, Any]:
        """Template variables for item conditions (same as the player's)."""
        s = self.screen
        screen = {"name": s.name, "zone": s.zone.name if s.zone_id else "", "room": s.room.name if s.room_id else "",
                  "venue": s.venue.name if s.venue_id else "", "tags": list(s.tags or []),
                  "groups": [g.name for g in s.groups()]} if s is not None else {
            "name": self.group.name if self.group else "", "zone": "", "room": "", "venue": "",
            "tags": list(self.group.match_tags or []) if self.group else [],
            "groups": [self.group.name] if self.group else []}
        return {"event": {"name": event.name, "slug": event.slug}, "screen": screen}


# ------------------------------------------------------------------ schedule windows
def schedule_windows(rule: ScheduleRule, start: dt.datetime, end: dt.datetime, tz: ZoneInfo) -> list[list[int]]:
    """Time windows (ms) of a rule between ``start`` and ``end``, merged and clipped."""
    out: list[list[int]] = []
    day = start.astimezone(tz).date() - dt.timedelta(days=1)
    last = end.astimezone(tz).date()
    weekdays = set(rule.weekdays or [])
    while day <= last:
        if ((not weekdays or day.weekday() in weekdays) and (rule.start_date is None or day >= rule.start_date)
                and (rule.end_date is None or day <= rule.end_date)):
            s = dt.datetime.combine(day, rule.start_time or dt.time(0), tzinfo=tz)
            if rule.end_time is None or (rule.start_time and rule.end_time <= rule.start_time):
                e_day = day + dt.timedelta(days=1)
                e = dt.datetime.combine(e_day, rule.end_time or dt.time(0), tzinfo=tz)
            else:
                e = dt.datetime.combine(day, rule.end_time, tzinfo=tz)
            s, e = max(s, start), min(e, end)
            if s < e:
                a, b = _ms(s), _ms(e)
                if out and a <= out[-1][1]:
                    out[-1][1] = max(out[-1][1], b)
                else:
                    out.append([a, b])
        day += dt.timedelta(days=1)
    return out


# ------------------------------------------------------------------ program
def _published_layouts(event) -> dict[str, int | None]:
    from apps.content.models import Layout

    out = {}
    for pk, data in Layout.objects.filter(event=event, published__isnull=False).values_list("pk",
                                                                                              "published__data"):
        d = (data or {}).get("duration")
        out[str(pk)] = int(d * 1000) if isinstance(d, int | float) and d > 0 else None
    return out


def playlist_payload(pl: Playlist) -> dict[str, Any]:
    return {
        "name": pl.name, "mode": pl.mode, "default": pl.default_duration * 1000,
        "items": [
            {"id": str(i.pk), **({"playlist": str(i.child_id)} if i.child_id else {"layout": str(i.layout_id)}),
             "duration": i.duration * 1000 if i.duration else None, "weight": i.weight, "tags": i.tags or [],
             "when": i.condition, "from": _ms(i.valid_from), "until": _ms(i.valid_until)}
            for i in pl.items.all() if i.enabled
        ],
    }


def _collect_playlists(event, roots: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    todo = set(roots)
    while todo:
        found = Playlist.objects.filter(event=event, pk__in=todo).prefetch_related("items")
        todo = set()
        for pl in found:
            out[str(pl.pk)] = payload = playlist_payload(pl)
            todo |= {i["playlist"] for i in payload["items"] if "playlist" in i and i["playlist"] not in out}
    return out


def message_layout(ov: Override, width: int = 1920, height: int = 1080) -> dict[str, Any]:
    """Built-in layout of a message override: title, message text, time; colours from the theme."""
    emergency = ov.level == Override.Level.EMERGENCY
    fg = "#ffffff" if emergency else "token:text"
    return {"format": 1, "width": width, "height": height,
            "background": {"color": "token:danger" if emergency else "token:background"},
            "elements": [
                {"id": "title", "type": "text", "name": "Title", "frame": {"x": 6, "y": 10, "w": 88, "h": 22},
                 "style": {"fontFamily": "token:heading", "fontSize": 11, "fontWeight": 800,
                           "color": fg if emergency else "token:accent"},
                 "props": {"text": ov.title, "autofit": True, "clamp": 2}},
                {"id": "text", "type": "text", "name": "Message", "frame": {"x": 6, "y": 36, "w": 88, "h": 50},
                 "style": {"fontSize": 6.5, "color": fg, "lineHeight": 1.3},
                 "props": {"text": ov.message, "autofit": True}},
                {"id": "clock", "type": "clock", "name": "Clock", "frame": {"x": 74, "y": 88, "w": 20, "h": 8},
                 "style": {"fontSize": 4.5, "textAlign": "right", "color": fg, "tabularNumbers": True},
                 "props": {"format": "HH:mm"}},
            ]}


def _default_entry(event) -> dict[str, Any] | None:
    pl = (Playlist.objects.filter(event=event, is_default=True).first()
          if modules.is_enabled("playlists", event) else None)
    if pl is not None:
        return {"id": "default", "source": "default", "name": pl.name, "priority": PRIORITY_DEFAULT,
                "content": {"playlist": str(pl.pk)}, "windows": [[None, None]]}
    from apps.content.models import Layout

    lay = Layout.objects.filter(event=event, is_default=True, published__isnull=False).first()
    if lay is not None:
        return {"id": "default", "source": "default", "name": lay.name, "priority": PRIORITY_DEFAULT,
                "content": {"layout": str(lay.pk)}, "windows": [[None, None]]}
    return None


def build_program(event, target: Target, *, now: dt.datetime | None = None, days: int = HORIZON_DAYS,
                  start: dt.datetime | None = None) -> dict[str, Any]:
    """Every entry that can apply to ``target`` from ``start`` (default: now) for ``days`` days."""
    now = now or timezone.now()
    start = start or now
    end = start + dt.timedelta(days=days)
    tz = _tz(event)
    entries: list[dict[str, Any]] = []
    messages: dict[str, Any] = {}
    if modules.is_enabled("overrides", event):
        for ov in (Override.objects.current(now).filter(event=event, starts_at__lt=end)
                   .select_related("layout", "playlist").prefetch_related("groups", "screens")):
            if not target.matches(ov):
                continue
            entries.append({"id": f"override:{ov.pk}", "source": "override", "name": ov.title,
                            "priority": ov.priority, "level": ov.level, "content": ov.content_ref(),
                            "windows": [[_ms(ov.starts_at), _ms(ov.expires_at)]]})
            if ov.is_message:
                size = (1080, 1920) if target.screen is not None and (
                    (target.screen.reported or {}).get("orientation") == "portrait") else (1920, 1080)
                messages[str(ov.pk)] = message_layout(ov, *size)
    if modules.is_enabled("schedules", event):
        for rule in (ScheduleRule.objects.filter(event=event, enabled=True)
                     .prefetch_related("groups", "screens")):
            if not target.matches(rule):
                continue
            windows = schedule_windows(rule, start, end, tz)
            if windows:
                entries.append({"id": f"schedule:{rule.pk}", "source": "schedule", "name": rule.name,
                                "priority": rule.effective_priority, "content": rule.content_ref(),
                                "windows": windows})
    default = _default_entry(event)
    if default is not None:
        entries.append(default)
    overlays: list[dict[str, Any]] = []
    for source in registry.ensure_loaded().program_sources:  # announcements, evacuation, ...
        extra = source(event, target, start, end) or {}
        entries.extend(extra.get("entries", []))
        messages.update(extra.get("messages", {}))
        overlays.extend(extra.get("overlays", []))
    roots = {e["content"]["playlist"] for e in entries if "playlist" in e["content"]}
    program = {"entries": entries, "playlists": _collect_playlists(event, roots),
               "layouts": _published_layouts(event), "messages": messages, "overlays": overlays,
               "horizon": _ms(end), "timezone": event.timezone}
    program["version"] = hashlib.sha256(json.dumps(program, sort_keys=True).encode()).hexdigest()[:16]
    return program


def screen_program(screen, now=None) -> dict[str, Any] | None:
    """The screen's program. With the playlists module off it still carries the default layout and what other
    modules contribute (announcements), so those reach screens too."""
    if not modules.is_enabled("content", screen.event):
        return None
    return build_program(screen.event, Target(screen=screen), now=now)


def now_playing(screen, at: dt.datetime | None = None) -> dict[str, Any] | None:
    """What a screen shows at ``at`` (server-side twin of the player; preview and dashboard)."""
    at = at or timezone.now()
    target = Target(screen=screen)
    program = build_program(screen.event, target, now=at, days=1)
    return describe(program, target.context(screen.event), _ms(at))


def describe(program: dict, ctx: dict, t: int) -> dict[str, Any] | None:
    slide = engine.slide_at(program, ctx, t)
    if slide is None:
        return None
    entry = next(e for e in program["entries"] if e["id"] == slide["entry"])
    return {**slide, "source": entry["source"], "name": entry["name"], "priority": entry["priority"],
            "level": entry.get("level", "")}


def timeline(program: dict, ctx: dict, start: int, end: int, limit: int = 200) -> list[dict[str, Any]]:
    """Consecutive slides between two times (preview "next hours" and the calendar)."""
    out: list[dict[str, Any]] = []
    t = start
    while t < end and len(out) < limit:
        slide = describe(program, ctx, t)
        nxt = engine.next_change(program, t, slide)
        stop = min(nxt if nxt is not None else end, end)
        if stop <= t:
            stop = t + 1000
        item = {**(slide or {"entry": None, "source": "nothing", "name": ""}), "from": t, "to": stop}
        if out and out[-1]["entry"] == item["entry"] and out[-1].get("layout") == item.get("layout") \
                and out[-1].get("index") == item.get("index"):
            out[-1]["to"] = stop
        else:
            out.append(item)
        t = stop
    return out


def segments(program: dict, ctx: dict, start: int, end: int) -> list[dict[str, Any]]:
    """Calendar blocks: which entry wins when (slides of one playlist merged)."""
    out: list[dict[str, Any]] = []
    t = start
    bounds = sorted({x for e in program["entries"] for w in e["windows"] for x in w
                     if x is not None and start < x < end} | {end})
    for b in bounds:
        found = describe_entry(program, ctx, t)
        if out and out[-1]["entry"] == (found or {}).get("id"):
            out[-1]["to"] = b
        else:
            out.append({"entry": (found or {}).get("id"), "name": (found or {}).get("name", ""),
                        "source": (found or {}).get("source", "nothing"), "from": t, "to": b})
        t = b
    return out


def describe_entry(program: dict, ctx: dict, t: int) -> dict[str, Any] | None:
    slide = engine.slide_at(program, ctx, t)
    if slide is None:
        return None
    return next(e for e in program["entries"] if e["id"] == slide["entry"])


def notify_screens(event) -> None:
    """Tell the event's screens to fetch their program again."""
    from apps.screens import channel
    from apps.screens.models import Screen

    for screen in Screen.objects.paired().filter(event=event):
        channel.send(screen, "program.changed", {})


# ------------------------------------------------------------------ playlists
def _check_cycle(playlist: Playlist, child: Playlist) -> None:
    seen, todo = set(), [child.pk]
    while todo:
        pk = todo.pop()
        if pk == playlist.pk:
            raise ValidationError(_("A playlist cannot contain itself (also not through other playlists)."))
        if pk in seen:
            continue
        seen.add(pk)
        todo += list(PlaylistItem.objects.filter(playlist_id=pk, child__isnull=False).values_list("child_id",
                                                                                                    flat=True))


def save_playlist(pl: Playlist, *, actor, request=None) -> Playlist:
    created = pl._state.adding
    pl.updated_by = actor
    with transaction.atomic():
        pl.save()
        if pl.is_default:
            Playlist.objects.filter(event=pl.event, is_default=True).exclude(pk=pl.pk).update(is_default=False)
    log(action="playlist.created" if created else "playlist.updated", actor=actor, target=pl, event=pl.event,
        request=request, message=f"Playlist {pl.name}",
        changes={"mode": pl.mode, "default_duration": pl.default_duration, "is_default": pl.is_default})
    notify_screens(pl.event)
    return pl


def delete_playlist(pl: Playlist, *, actor, request=None) -> None:
    if ScheduleRule.objects.filter(playlist=pl).exists() or Override.objects.current().filter(playlist=pl).exists():
        raise ValidationError(_("This playlist is used by a schedule or an active override."))
    log(action="playlist.deleted", actor=actor, target=pl, event=pl.event, request=request,
        message=f"Playlist {pl.name} deleted")
    event = pl.event
    pl.delete()
    notify_screens(event)


def save_item(item: PlaylistItem, *, actor, request=None) -> PlaylistItem:
    item.full_clean(exclude=["playlist"])
    pl = item.playlist
    if item.child_id:
        if item.child.event_id != pl.event_id:
            raise ValidationError(_("Unknown playlist."))
        _check_cycle(pl, item.child)
    if item.layout_id and item.layout.event_id != pl.event_id:
        raise ValidationError(_("Unknown layout."))
    created = item._state.adding
    if created:
        last = pl.items.order_by("-position").values_list("position", flat=True).first()
        item.position = (last or 0) + 1
    item.save()
    log(action="playlist.item_added" if created else "playlist.item_changed", actor=actor, target=pl,
        event=pl.event, request=request, message=f"{pl.name}: {item}",
        changes={"item": str(item.pk), "duration": item.duration, "weight": item.weight, "tags": item.tags,
                 "condition": item.condition, "enabled": item.enabled})
    notify_screens(pl.event)
    return item


def move_item(item: PlaylistItem, delta: int, *, actor, request=None) -> None:
    items = list(item.playlist.items.all())
    i = next(n for n, x in enumerate(items) if x.pk == item.pk)
    j = max(0, min(len(items) - 1, i + delta))
    if i == j:
        return
    items.insert(j, items.pop(i))
    for n, x in enumerate(items):
        if x.position != n:
            x.position = n
            x.save(update_fields=["position"])
    log(action="playlist.reordered", actor=actor, target=item.playlist, event=item.playlist.event, request=request,
        message=f"{item.playlist.name}: {item} moved")
    notify_screens(item.playlist.event)


def delete_item(item: PlaylistItem, *, actor, request=None) -> None:
    pl = item.playlist
    log(action="playlist.item_removed", actor=actor, target=pl, event=pl.event, request=request,
        message=f"{pl.name}: {item} removed")
    item.delete()
    notify_screens(pl.event)


# ------------------------------------------------------------------ schedules
def save_rule(rule: ScheduleRule, *, actor, request=None, m2m: dict | None = None) -> ScheduleRule:
    created = rule._state.adding
    rule.updated_by = actor
    rule.full_clean(exclude=["groups", "screens"])
    with transaction.atomic():
        rule.save()
        for name, values in (m2m or {}).items():
            getattr(rule, name).set(values)
    log(action="schedule.created" if created else "schedule.updated", actor=actor, target=rule, event=rule.event,
        request=request, message=f"Schedule {rule.name}",
        changes={"content": rule.content_label(), "target": rule.target_label(), "weekdays": rule.weekdays,
                 "time": f"{rule.start_time or ''}-{rule.end_time or ''}",
                 "dates": f"{rule.start_date or ''}-{rule.end_date or ''}", "priority": rule.priority,
                 "enabled": rule.enabled})
    notify_screens(rule.event)
    return rule


def delete_rule(rule: ScheduleRule, *, actor, request=None) -> None:
    log(action="schedule.deleted", actor=actor, target=rule, event=rule.event, request=request,
        message=f"Schedule {rule.name} deleted")
    event = rule.event
    rule.delete()
    notify_screens(event)


# ------------------------------------------------------------------ overrides
def push_override(ov: Override, *, actor, request=None, m2m: dict | None = None) -> Override:
    if ov.is_message and not (ov.message or "").strip():
        raise ValidationError(_("Choose a layout or playlist, or write a message."))
    if ov.expires_at and ov.expires_at <= ov.starts_at:
        raise ValidationError(_("The end must be after the start."))
    ov.created_by = actor
    with transaction.atomic():
        ov.save()
        for name, values in (m2m or {}).items():
            getattr(ov, name).set(values)
        if not (ov.all_screens or ov.groups.exists() or ov.screens.exists()):
            raise ValidationError(_("Choose the screens."))
    log(action="override.pushed", actor=actor, target=ov, event=ov.event, request=request,
        message=f"Override {ov.title} ({ov.level}) on {ov.target_label()}",
        changes={"level": ov.level, "content": ov.content_label(), "target": ov.target_label(),
                 "starts_at": ov.starts_at, "expires_at": ov.expires_at})
    webhooks.emit("override.started", override_payload(ov), event=ov.event)
    notify_screens(ov.event)
    return ov


def cancel_override(ov: Override, *, actor, request=None) -> None:
    if ov.cancelled_at:
        return
    ov.cancelled_at = timezone.now()
    ov.cancelled_by = actor
    ov.save(update_fields=["cancelled_at", "cancelled_by"])
    log(action="override.cancelled", actor=actor, target=ov, event=ov.event, request=request,
        message=f"Override {ov.title} cancelled")
    webhooks.emit("override.cancelled", override_payload(ov), event=ov.event)
    notify_screens(ov.event)


def override_payload(ov: Override) -> dict[str, Any]:
    return {"id": str(ov.pk), "title": ov.title, "level": ov.level, "content": ov.content_ref(),
            "target": {"all": ov.all_screens, "groups": [str(g.pk) for g in ov.groups.all()],
                       "screens": [str(s.pk) for s in ov.screens.all()]},
            "starts_at": ov.starts_at.isoformat(),
            "expires_at": ov.expires_at.isoformat() if ov.expires_at else None, "state": ov.state()}


def may_target(user, event, perm: str, *, all_screens: bool, groups, screens, request=None) -> bool:
    """Scoped permissions: everything needs the permission without scope; groups/screens their own scope."""
    from apps.events import rbac

    if all_screens:
        return rbac.has_perm(user, event, perm, request=request)
    return all(rbac.has_perm(user, event, perm, obj=o, request=request) for o in [*groups, *screens])
