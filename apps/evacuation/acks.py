# SPDX-License-Identifier: AGPL-3.0-or-later
"""Acknowledgements (brief §8.5, roadmap 3.8, ADR-0035): screens confirm what they rendered, staff answer alarms.

The control room sees "X of Y screens confirmed / Z offline" for the current message, per zone, and the
trigger-to-render time (p95) of the last changes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import audit

from .models import LatencySample, ScreenAck, StaffAck

#: render times above this are measurement errors (clock jumps), not latency
MAX_LATENCY_MS = 600_000


def _ts(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.get_current_timezone())
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def record(screen: Any, data: dict[str, Any]) -> ScreenAck:
    """``{"seq", "v", "state", "drill", "rendered_at": ms, "issued": ms, "via", "fallback", "detail"}`` from a
    player. Times are the player's server-synchronised clock (milliseconds)."""
    try:
        seq = max(int(data.get("seq") or 0), 0)
    except (TypeError, ValueError):
        seq = 0
    rendered = _ts(data.get("rendered_at")) or timezone.now()
    latency = None
    try:
        issued = float(data.get("issued") or 0)
        rendered_ms = float(data.get("rendered_at") or 0)
        if issued > 0 and rendered_ms >= issued:
            latency = int(rendered_ms - issued)
    except (TypeError, ValueError):
        latency = None
    if latency is not None and latency > MAX_LATENCY_MS:
        latency = None
    ack: ScreenAck
    ack, _created = ScreenAck.objects.update_or_create(screen_id=screen.pk, defaults={
        "event": screen.event, "seq": seq, "version": str(data.get("v") or "")[:32],
        "state": str(data.get("state") or "")[:20], "drill": bool(data.get("drill")),
        "via": str(data.get("via") or "")[:20], "rendered_at": rendered, "latency_ms": latency,
        "fallback": bool(data.get("fallback")), "detail": str(data.get("detail") or "")[:200]})
    if latency is not None and seq:
        LatencySample.objects.get_or_create(event=screen.event, seq=seq, screen_id=screen.pk,
                                            defaults={"latency_ms": latency})
    return ack


def p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


@dataclass
class Coverage:
    total: int
    confirmed: int
    offline: int
    pending: int
    zones: list[dict[str, Any]]
    seq: int
    p95_ms: int | None
    last_p95_ms: int | None
    samples: int
    fallback: int


def coverage(event: Any) -> Coverage:
    """How many participating screens show the current message: confirmed / waiting / offline, per zone."""
    from django.apps import apps

    from . import feed

    seq = feed.current_seq(event)
    screens: list[Any] = []
    if apps.is_installed("apps.screens"):
        from apps.screens.models import Screen

        screens = list(Screen.objects.paired().filter(event=event).select_related("zone")
                       .prefetch_related("room__zones"))
    acks = {str(a.screen_id): a for a in ScreenAck.objects.filter(event=event)}
    per_zone: dict[str, dict[str, Any]] = {}
    total = confirmed = offline = fallback = 0
    for s in screens:
        if feed._role(s) == "excluded":
            continue
        total += 1
        a = acks.get(str(s.pk))
        ok = a is not None and a.seq >= seq
        off = s.health_state in ("offline", "stale") and not ok
        confirmed += ok
        offline += off
        fallback += bool(ok and a and a.fallback)
        zone_names = [s.zone.name] if s.zone_id else []
        if s.room_id:
            zone_names += [z.name for z in s.room.zones.all() if z.name not in zone_names]
        for name in zone_names or ["—"]:
            row = per_zone.setdefault(name, {"zone": name, "total": 0, "confirmed": 0, "offline": 0})
            row["total"] += 1
            row["confirmed"] += ok
            row["offline"] += off
    recent = list(LatencySample.objects.filter(event=event, at__gte=timezone.now() - timedelta(days=1))
                  .values_list("latency_ms", flat=True)[:5000])
    last = list(LatencySample.objects.filter(event=event, seq=seq).values_list("latency_ms", flat=True))
    return Coverage(total, confirmed, offline, total - confirmed - offline, sorted(per_zone.values(),
                    key=lambda r: r["zone"]), seq, p95(recent), p95(last), len(recent), fallback)


def staff_ack(event: Any, user: Any, kind: str, *, zone: Any = None, note: str = "", request: Any = None) -> StaffAck:
    from . import feed, services

    if kind not in dict(StaffAck.KINDS):
        raise ValueError(kind)
    shown = services.effective_for(event, [str(zone.pk)] if zone else [])
    row: StaffAck = StaffAck.objects.create(event=event, user=user, user_repr=str(user)[:200], kind=kind, zone=zone,
                                  note=note[:300], seq=feed.current_seq(event), drill=shown.drill)
    audit.log(action=f"evacuation.staff_{kind}", actor=user, event=event, target=row, request=request,
              drill=shown.drill, message=f"{user}: {row.get_kind_display()}" + (f" ({zone.name})" if zone else ""))
    if kind == "need_help":
        from django.urls import reverse

        from apps.core.notify import notify

        from . import triggers

        notify([u for u in triggers.control_room(event, zone) if u != user],
               str(_("Need help: %(who)s") % {"who": user}),
               body=(zone.name if zone else str(_("whole event"))) + (f" · {note[:300]}" if note else ""),
               level="err", event=event, url=reverse("evacuation:index", args=[event.slug]))
    from apps.core import webhooks

    webhooks.emit("evacuation.staff_ack", {"event": event.slug, "kind": kind, "zone": str(zone.pk) if zone else None,
                                          "user": str(user), "note": note[:300], "drill": shown.drill}, event=event)
    return row


def recent_staff(event: Any, since: Any = None) -> list[StaffAck]:
    qs = StaffAck.objects.filter(event=event).select_related("zone")
    if since is not None:
        qs = qs.filter(at__gte=since)
    return list(qs[:50])


def alarm_since(event: Any) -> Any:
    """When the running alarm started: per scope in alarm, its last change from a non-alarm state into an
    alarm (stepping up or down between alarm stages keeps the start); the earliest of those. ``None`` without
    an alarm."""
    from . import machine, services
    from .models import StateChange

    now = timezone.now()
    ev, zones = services.statuses(event)
    alarms = [s.value for s in machine.ALARMS]
    starts: list[datetime] = []
    for zone_id, status in [(None, ev), *zones.items()]:
        if not machine.current(status, now).alarm:
            continue
        change = (StateChange.objects.filter(event=event, zone_id=zone_id, to_state__in=alarms)
                  .exclude(from_state__in=alarms).order_by("-at").first())
        start = change.at if change else status.since
        if start is not None:
            starts.append(start)
    return min(starts) if starts else None


def screen_acks(event: Any) -> dict[str, ScreenAck]:
    return {str(a.screen_id): a for a in ScreenAck.objects.filter(event=event)}
