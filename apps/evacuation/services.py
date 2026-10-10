# SPDX-License-Identifier: AGPL-3.0-or-later
"""All evacuation state changes go through :func:`change` (ADR-0029)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.core import audit, settings_store, webhooks
from apps.events import rbac

from . import machine
from .machine import Kind, Refused, State
from .models import EvacState, StateChange

STATE_CHANGED = "evacuation.state_changed"
PERM_TRIGGER = "evacuation.trigger"
PERM_CLEAR = "evacuation.clear"
PERM_DRILL = "evacuation.drill"


@dataclass(frozen=True)
class Config:
    enabled: frozenset[State]
    clear_seconds: int
    labels: dict[str, str]
    drill_text: str


DEFAULT_LABELS = {
    "normal": "Normal", "staff_alert": "Staff alert", "attention": "Attention",
    "shelter_in_place": "Shelter in place", "evacuate": "Evacuate", "all_clear": "All clear",
}


def config(event: Any) -> Config:
    cfg = settings_store.get("evacuation", event=event)
    enabled = set(machine.ALWAYS_ENABLED)
    for state, key in ((State.STAFF_ALERT, "staff_alert"), (State.ATTENTION, "attention"),
                       (State.SHELTER, "shelter_in_place")):
        if cfg.get(f"{key}_enabled", True):
            enabled.add(state)
    labels = {k: (cfg.get(f"{k}_label") or v) for k, v in DEFAULT_LABELS.items()}
    return Config(frozenset(enabled), int(cfg.get("all_clear_minutes", 5)) * 60, labels,
                  str(cfg.get("drill_text") or "DRILL"))


def zones_of(event: Any) -> Any:
    from apps.venues.models import Zone

    return Zone.objects.filter(venue__events=event).select_related("venue").order_by("venue__name", "name")


def _row(event: Any, zone: Any) -> EvacState:
    row: EvacState = EvacState.objects.select_for_update().get_or_create(event=event, zone=zone)[0]
    return row


def statuses(event: Any) -> tuple[machine.Status, dict[str, machine.Status]]:
    """The event status and the status of every zone that has one."""
    ev = machine.NORMAL
    zones: dict[str, machine.Status] = {}
    for row in EvacState.objects.filter(event=event):
        if row.zone_id is None:
            ev = row.status
        else:
            zones[str(row.zone_id)] = row.status
    return ev, zones


def effective_for(event: Any, zone_ids: list[str], now: Any = None) -> machine.Status:
    """What a screen in ``zone_ids`` shows now (event status and its zones, highest severity wins)."""
    now = now or timezone.now()
    ev, zones = statuses(event)
    return machine.effective([ev] + [zones[z] for z in zone_ids if z in zones], now)


def can(user: Any, event: Any, target: State, *, drill: bool, zone: Any = None, request: Any = None) -> bool:
    perm = PERM_DRILL if drill else (PERM_CLEAR if target in (State.ALL_CLEAR, State.NORMAL) else PERM_TRIGGER)
    if zone is None:
        return rbac.has_perm(user, event, perm, request=request)
    return rbac.has_perm(user, event, perm, obj=zone, request=request)


def _record(event: Any, row: EvacState, change: machine.Change, *, actor: Any, source: str, reason: str,
            request: Any) -> StateChange:
    row.apply(change.after)
    row.changed_by = actor if getattr(actor, "pk", None) else None
    row.source, row.reason = source, reason[:300]
    row.save()
    zone = row.zone
    entry: StateChange = StateChange.objects.create(
        event=event, zone=zone, zone_name=zone.name if zone else "", at=change.after.since or timezone.now(),
        kind=change.kind.value, from_state=change.before.state.value, from_drill=change.before.drill,
        to_state=change.after.state.value, drill=change.after.drill if change.after.state is not State.NORMAL
        else change.before.drill, actor=row.changed_by, actor_repr=str(actor)[:200] if actor else source,
        source=source, reason=reason[:300])
    audit.log(action=f"evacuation.{change.kind.value}", actor=row.changed_by, event=event, target=row,
              request=request, drill=entry.drill,
              message=f"{zone.name if zone else 'Event'}: {change.before.state.value} -> {change.after.state.value}"
                      + (" (drill)" if entry.drill else ""),
              changes={"state": [change.before.state.value, change.after.state.value],
                       "drill": [change.before.drill, change.after.drill]},
              scope={"zone": str(zone.pk)} if zone else {"zone": None, "source": source})
    payload = payload_of(event, row, change.kind)
    transaction.on_commit(lambda: webhooks.emit(STATE_CHANGED, payload, event=event))
    return entry


def payload_of(event: Any, row: EvacState, kind: Kind | None = None) -> dict[str, Any]:
    return {"event": event.slug, "zone": str(row.zone_id) if row.zone_id else None,
            "zone_name": row.zone.name if row.zone_id else None, "state": row.state, "drill": row.drill,
            "since": row.since.isoformat() if row.since else None,
            "clear_until": row.clear_until.isoformat() if row.clear_until else None,
            "version": row.version, "kind": kind.value if kind else None}


def change(event: Any, target: State | str, *, zone: Any = None, drill: bool = False, actor: Any = None,
           request: Any = None, source: str = "web", reason: str = "", clear_zones: list[str] | None = None,
           check_perms: bool = True) -> list[StateChange]:
    """Change the event's (``zone=None``) or a zone's state. Returns the history entries written.

    ``clear_zones``: for an event-wide all clear, the zones (ids) to clear as well; ``None`` clears every zone in
    alarm. Raises :class:`Refused` or ``PermissionDenied``.
    """
    target = State(target)
    if zone is not None and not zones_of(event).filter(pk=zone.pk).exists():
        raise Refused("zone", "This zone is not part of the event.")
    cfg = config(event)
    now = timezone.now()
    out: list[StateChange] = []
    with transaction.atomic():
        row = _row(event, zone)
        # ending something needs the permission for what is ending (a drill or a real alarm)
        kind_drill = row.drill if target in (State.ALL_CLEAR, State.NORMAL) else drill
        if check_perms and actor is not None and not can(actor, event, target, drill=kind_drill, zone=zone,
                                                         request=request):
            raise PermissionDenied("evacuation")
        others = list(EvacState.objects.select_for_update().filter(event=event).exclude(pk=row.pk)
                      .select_related("zone"))
        elsewhere = any(machine.current(o.status, now).real_alarm for o in others)
        result = machine.transition(row.status, target, drill=drill, now=now, enabled=cfg.enabled,
                                    clear_seconds=cfg.clear_seconds, real_alarm_elsewhere=elsewhere)
        kw = {"actor": actor, "source": source, "reason": reason, "request": request}
        out.append(_record(event, row, result, **kw))
        if result.after.real_alarm:
            # a real alarm ends every drill in the event, so no drill can be mistaken for it
            for other in others:
                ended = machine.end_drill(other.status, now)
                if ended is not None:
                    out.append(_record(event, other, ended, **kw))
        elif target is State.ALL_CLEAR and zone is None:
            wanted = None if clear_zones is None else set(clear_zones)
            for other in others:
                if (wanted is None or str(other.zone_id) in wanted) and machine.current(other.status, now).alarm:
                    if check_perms and actor is not None and not can(actor, event, State.ALL_CLEAR,
                                                                      drill=other.drill, zone=other.zone,
                                                                      request=request):
                        continue
                    sub = machine.transition(other.status, State.ALL_CLEAR, drill=other.drill, now=now,
                                             clear_seconds=cfg.clear_seconds)
                    out.append(_record(event, other, sub, **kw))
    return out


__all__ = ["Refused", "change", "config", "effective_for", "statuses", "can", "STATE_CHANGED"]
