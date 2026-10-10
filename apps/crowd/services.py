# SPDX-License-Identifier: AGPL-3.0-or-later
"""Occupancy services (ADR-0040): counting, the capacity rule, history, alerts and what screens show.

``count`` and ``set_value`` are the only ways the number changes; both run in a transaction with the area row
locked, so clicks from several door counters and sensor messages add up exactly. ``client_id`` (a click queued in
the staff app while offline, a sensor message id) makes a replay harmless.

The rule: an area is *busy* from ``busy_percent`` and *full* from ``full_percent`` of its capacity; it stays full
until the count falls below ``release_percent`` (hysteresis, so the sign does not flicker at the limit). When it
becomes full or opens again: screens in the area's room/zone (and chosen screen groups) get or lose the "full"
banner within a second (``program.changed``), the roles to alert get a notification, the channels a message, and
the ops log a line (webhook ``occupancy.state_changed``).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import modules, webhooks
from apps.core.audit import log

from .models import Area, CountEvent, Sample

MODULE = "crowd"
MAX_STEP = 10_000
RANK = 25  # banner rank: above "important" announcements (20), below "urgent" (30)


def _user(actor: Any) -> Any:
    return actor if getattr(actor, "pk", None) and getattr(actor, "is_authenticated", True) else None


def state_for(area: Area, value: int, current: str) -> str:
    """The rule (pure): busy/full by percentage, full released only below ``release_percent``."""
    if not area.capacity:
        return Area.State.NORMAL
    pct = value * 100 / area.capacity
    release = min(area.release_percent, area.full_percent)
    if pct >= area.full_percent or (current == Area.State.FULL and pct >= release):
        return Area.State.FULL
    if pct >= area.busy_percent:
        return Area.State.BUSY
    return Area.State.NORMAL


def payload_of(area: Area) -> dict[str, Any]:
    return {"id": str(area.pk), "event": area.event.slug, "name": area.name, "value": area.value,
            "capacity": area.capacity, "percent": area.percent, "state": area.state,
            "room": str(area.room_id) if area.room_id else None, "zone": str(area.zone_id) if area.zone_id else None,
            "since": area.state_since.isoformat() if area.state_since else None}


# ------------------------------------------------------------------ counting
def count(area: Area, delta: int, *, source: str, device: str = "", client_id: str = "",
          at: dt.datetime | None = None, actor: Any = None) -> Area:
    """Add ``delta`` (people in: positive, out: negative). The count never goes below zero."""
    delta = int(delta)
    if abs(delta) > MAX_STEP:
        raise ValidationError(_("That is too many people at once."))
    return _apply(area, lambda v: max(0, v + delta), source=source, device=device, client_id=client_id, at=at,
                  actor=None)


def set_value(area: Area, value: int, *, source: str, device: str = "", client_id: str = "",
              at: dt.datetime | None = None, actor: Any = None, request: Any = None) -> Area:
    """Set the number (a sensor that reports the occupancy, or a correction by staff)."""
    value = int(value)
    if value < 0 or value > 1_000_000:
        raise ValidationError(_("Give a number of people (0 or more)."))
    before = area.value
    out = _apply(area, lambda v: value, source=source, device=device, client_id=client_id, at=at,
                 actor=actor if source == CountEvent.Source.CORRECTION else None)
    if source == CountEvent.Source.CORRECTION:
        log(action="crowd.corrected", actor=actor, target=out, event=out.event, request=request,
            message=f"{out.name}: {before} → {value}", changes={"value": [before, value]})
    return out


def _apply(area: Area, fn: Any, *, source: str, device: str, client_id: str, at: dt.datetime | None,
           actor: Any) -> Area:
    client_id = (client_id or "")[:64]
    now = timezone.now()
    when = min(at, now) if at is not None and at > now - dt.timedelta(hours=12) else now
    try:
        with transaction.atomic():
            a = Area.objects.select_for_update().select_related("event").get(pk=area.pk)
            if client_id and CountEvent.objects.filter(area=a, client_id=client_id).exists():
                return a  # a replay
            new = fn(a.value)
            ev = CountEvent.objects.create(area=a, at=when, delta=new - a.value, value_after=new, source=source,
                                           device=device[:80], user=_user(actor), client_id=client_id)
            a.value = new
            a.updated_at = now
            a.version += 1
            previous = a.state
            a.state = state_for(a, new, previous)
            if a.state != previous:
                a.state_since = now
            a.save(update_fields=["value", "updated_at", "version", "state", "state_since"])
            _sample(a, when, new)
            if a.state != previous:
                _changed(a, previous)
            transaction.on_commit(lambda: _live(a, ev))
    except IntegrityError:  # the same client id arrived twice at the same moment
        return Area.objects.get(pk=area.pk)
    area.value, area.state, area.state_since, area.version = a.value, a.state, a.state_since, a.version
    return a


def _sample(area: Area, at: dt.datetime, value: int) -> None:
    minute = at.replace(second=0, microsecond=0)
    s = Sample.objects.filter(area=area, minute=minute).first()
    if s is None:
        Sample.objects.create(area=area, minute=minute, value=value, peak=value, low=value)
    else:
        s.value, s.peak, s.low = value, max(s.peak, value), min(s.low, value)
        s.save(update_fields=["value", "peak", "low"])


def _live(area: Area, ev: CountEvent) -> None:
    """Every count: the control room and open counter pages update (realtime stream)."""
    from apps.core import realtime

    realtime.publish(area.event, "occupancy.count", {**payload_of(area), "delta": ev.delta, "source": ev.source})


# ------------------------------------------------------------------ the rule fired
def _changed(area: Area, previous: str) -> None:
    payload = {**payload_of(area), "previous": previous}
    log(action=f"crowd.{area.state}", target=area, event=area.event,
        message=f"{area.name}: {Area.State(area.state).label} ({area.value} / {area.capacity})",
        changes={"state": [previous, area.state], "value": area.value})

    def after() -> None:
        webhooks.emit("occupancy.state_changed", payload, event=area.event)
        if area.show_on_screens and Area.State.FULL in (area.state, previous):
            push_screens(area.event)
        if Area.State.FULL in (area.state, previous):
            _alert(area, previous)
    transaction.on_commit(after)


def push_screens(event: Any) -> int:
    """Screens refetch their program: the "full" banners are part of it (``program_source``). Every screen of
    the event, because an area full elsewhere changes the suggestion on others."""
    from django.apps import apps

    if not apps.is_installed("apps.screens"):
        return 0
    from apps.screens import channel
    from apps.screens.models import Screen

    ids = list(Screen.objects.paired().filter(event=event).values_list("pk", flat=True))
    return channel.send_many([(sid, "program.changed", {}) for sid in ids]) if ids else 0


def _alert(area: Area, previous: str) -> None:
    from django.urls import reverse

    from apps.core import alerts
    from apps.core.notify import notify
    from apps.core.plugins import Alert
    from apps.events import rbac
    from apps.events.models import RoleAssignment

    full = area.state == Area.State.FULL
    title = (_("%(a)s is full (%(v)s / %(c)s)") if full else _("%(a)s has space again (%(v)s / %(c)s)")) % {
        "a": area.name, "v": area.value, "c": area.capacity}
    body = suggestion(area) if full else ""
    url = reverse("crowd:area", args=[area.event.slug, area.pk])
    role_ids = list(area.notify_roles.values_list("pk", flat=True))
    users = {a.membership.user for a in RoleAssignment.objects.filter(role_id__in=role_ids).select_related(
        "membership__user") if a.membership.user.is_active} if role_ids else set()
    users = {u for u in users if "crowd.view" in rbac.effective(u, area.event, two_factor=True).permissions}
    notify(list(users), title, body=body, url=url, level="warn" if full else "info", event=area.event)
    alerts.enqueue(area.event, list(area.channels or []),
                   Alert(title=title, body=body, level="warn" if full else "info", url=url,
                         key=f"crowd:{area.pk}:{area.version}"))


# ------------------------------------------------------------------ screens
def suggestion(area: Area) -> str:
    if area.full_text.strip():
        return area.full_text.strip()
    alt = area.alternative
    if alt is not None and alt.pk != area.pk and alt.state != Area.State.FULL:
        return _("%(a)s is full. Please use %(b)s.") % {"a": area.name, "b": alt.name}
    return _("%(a)s is full. Please wait or come back later.") % {"a": area.name}


def applies_to(area: Area, target: Any, groups: set[Any]) -> bool:
    screen = getattr(target, "screen", None)
    if groups & set(getattr(target, "group_ids", set())):
        return True
    if screen is None:
        return False
    return bool((area.room_id and screen.room_id == area.room_id)
                or (area.zone_id and screen.zone_id == area.zone_id))


def program_source(event: Any, target: Any, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    """"Full" banners for one screen's program (``r.program_source``): open-ended while the area is full."""
    out: dict[str, Any] = {"entries": [], "messages": {}, "overlays": []}
    if not modules.is_enabled(MODULE, event):
        return out
    for area in (Area.objects.filter(event=event, state=Area.State.FULL, show_on_screens=True)
                 .select_related("alternative").prefetch_related("screen_groups")):
        groups = {g.pk for g in area.screen_groups.all()}
        if not applies_to(area, target, groups):
            continue
        out["overlays"].append({"id": f"crowd:{area.pk}", "style": "banner", "rank": RANK,
                                "level": _("%(a)s full") % {"a": area.name}, "colour": "#b91c1c", "sound": "",
                                "title": _("%(a)s is full") % {"a": area.name}, "text": suggestion(area),
                                "windows": [[None, None]]})
    return out


# ------------------------------------------------------------------ editing
def save_area(area: Area, *, actor: Any, request: Any = None, m2m: dict[str, Any] | None = None) -> Area:
    if not area.name.strip():
        raise ValidationError(_("Give the area a name."))
    if area.capacity and not (0 < area.busy_percent <= area.full_percent):
        raise ValidationError(_("“Busy” must start at or below “full”."))
    if area.alternative_id and area.alternative_id == area.pk:
        raise ValidationError(_("An area cannot send people to itself."))
    created = area._state.adding
    before = area.state
    area.state = state_for(area, area.value, area.state)
    if area.state != before:
        area.state_since = timezone.now()
    area.version += 1
    area.save()
    for name, values in (m2m or {}).items():
        getattr(area, name).set(values)
    log(action="crowd.area_created" if created else "crowd.area_edited", actor=actor, target=area, event=area.event,
        request=request, message=area.name, changes={"capacity": area.capacity, "busy": area.busy_percent,
                                                     "full": area.full_percent, "release": area.release_percent})
    if area.state != before:
        _changed(area, before)
    elif not created:
        transaction.on_commit(lambda: push_screens(area.event))  # text or targets may have changed
    return area


def delete_area(area: Area, *, actor: Any, request: Any = None) -> None:
    event, was_full = area.event, area.state == Area.State.FULL
    log(action="crowd.area_deleted", actor=actor, target=area, event=event, request=request, message=area.name)
    area.delete()
    if was_full:
        transaction.on_commit(lambda: push_screens(event))


def reset_all(event: Any, *, actor: Any, request: Any = None) -> int:
    """Set every area to 0 (start of a day). Each reset is a correction in the history."""
    n = 0
    for area in Area.objects.filter(event=event).exclude(value=0):
        set_value(area, 0, source=CountEvent.Source.CORRECTION, actor=actor, request=request, device="reset")
        n += 1
    return n


# ------------------------------------------------------------------ history
def history(area: Area, *, hours: int = 12, now: dt.datetime | None = None) -> list[Sample]:
    now = now or timezone.now()
    return list(Sample.objects.filter(area=area, minute__gte=now - dt.timedelta(hours=hours)))


def chart(area: Area, samples: list[Sample], *, now: dt.datetime | None = None, hours: int = 12,
          width: int = 720, height: int = 220) -> dict[str, Any]:
    """An SVG line chart (server-side, no script): the count over the last hours with the capacity lines."""
    now = now or timezone.now()
    start = now - dt.timedelta(hours=hours)
    top = max([area.capacity * 1.1 if area.capacity else 0] + [s.peak for s in samples] + [area.value, 10])
    pad_l, pad_b = 44, 22

    def x(t: dt.datetime) -> float:
        return pad_l + (width - pad_l - 6) * max(0.0, min(1.0, (t - start).total_seconds() / (hours * 3600)))

    def y(v: float) -> float:
        return 6 + (height - pad_b - 6) * (1 - v / top)

    pts: list[str] = []
    last = samples[0].value if samples and samples[0].minute <= start else 0
    pts.append(f"{x(start):.1f},{y(last):.1f}")
    for s in samples:
        pts.append(f"{x(s.minute):.1f},{y(last):.1f}")  # steps: the value holds until it changes
        pts.append(f"{x(s.minute):.1f},{y(s.value):.1f}")
        last = s.value
    pts.append(f"{x(now):.1f},{y(area.value):.1f}")
    lines = []
    if area.capacity:
        for pct, cls in ((area.full_percent, "full"), (area.busy_percent, "busy")):
            v = area.capacity * pct / 100
            lines.append({"y": f"{y(v):.1f}", "cls": cls, "label": f"{pct}% ({round(v)})"})
    ticks = []
    t = start.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
    step = max(1, hours // 6)
    while t <= now:
        ticks.append({"x": f"{x(t):.1f}", "label": timezone.localtime(t).strftime("%H:%M")})
        t += dt.timedelta(hours=step)
    peak = max([s.peak for s in samples] + [area.value])
    return {"width": width, "height": height, "points": " ".join(pts), "lines": lines, "ticks": ticks,
            "ymax": round(top), "ytop": "6", "ybase": f"{height - pad_b}", "xl": pad_l, "xr": width - 6,
            "peak": peak}
