# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trigger sources, policies, armed requests and the two-person rule (brief §8.3, ADR-0031).

:func:`trigger` is the entry point for every source (control room, panic page, API, bridge, schedule,
extensions). It checks the change, then follows the policy: execute, arm (a request the control room confirms;
auto-escalation executes it when nobody answers in time) or notify. A person's change into a stage under the
two-person rule waits for a second person and expires when nobody confirms. :func:`process_due` runs every few
seconds (Celery beat) and when the control page loads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import audit, settings_store
from apps.events import rbac

from . import machine, policy, services
from .machine import Refused, State
from .models import EvacPolicy, EvacRequest, EvacState, ScheduledDrill, StateChange

#: a scheduled drill that should have started longer ago than this is not started late (server was down)
DRILL_GRACE = timedelta(minutes=15)


@dataclass
class Outcome:
    result: str  # executed | armed | waiting | notified | duplicate
    changes: list[StateChange] = field(default_factory=list)
    request: EvacRequest | None = None


def sources() -> list[tuple[str, str]]:
    from apps.core.registry import registry

    out = [(policy.WEB, _("Control room page")), (policy.PANIC, _("Panic page (staff app)")),
           (policy.API, _("API / external systems")), (policy.BRIDGE, _("Hardware bridge")),
           (policy.SCHEDULE, _("Scheduled drills"))]
    known = {k for k, _n in out}
    out += [(k, spec.name) for k, spec in sorted(registry.ensure_loaded().evac_triggers.items()) if k not in known]
    return out


def rules(event: Any) -> list[policy.Rule]:
    return [policy.Rule(p.source, policy.Action(p.action), p.state, str(p.zone_id) if p.zone_id else "",
                        p.escalate_seconds) for p in EvacPolicy.objects.filter(event=event)]


def two_person(event: Any) -> tuple[frozenset[str], int]:
    cfg = settings_store.get("evacuation", event=event)
    return frozenset(cfg.get("two_person_states") or []), int(cfg.get("two_person_seconds") or 60)


def control_room(event: Any, zone: Any = None) -> list[Any]:
    """People who may confirm alarms (with two factors where their role needs them), for notifications."""
    from apps.events.models import Membership

    chain = zone.evac_scope_chain() if zone is not None else None
    out = []
    for m in Membership.objects.filter(event=event).select_related("user"):
        if m.user.is_active and rbac.effective(m.user, event, two_factor=True).access.allows(
                services.PERM_TRIGGER, chain):
            out.append(m.user)
    return out


def _alert(event: Any, req: EvacRequest, title: str, level: str = "err") -> None:
    from django.urls import reverse

    from apps.core.notify import notify

    where = req.zone.name if req.zone_id else _("whole event")
    body = f"{req.get_state_display()} · {where}" + (" (drill)" if req.drill else "") + (
        f" · {req.reason}" if req.reason else "")
    notify(control_room(event, req.zone), title, body=body, level=level, event=event,
           url=reverse("evacuation:index", args=[event.slug]))


def _who(actor: Any, source: str) -> str:
    return str(actor)[:200] if actor is not None else source


def trigger(event: Any, target: State | str, *, source: str, zone: Any = None, drill: bool = False,
            actor: Any = None, request: Any = None, reason: str = "", key: str = "",
            clear_zones: list[str] | None = None, check_perms: bool = True, execute: bool = False) -> Outcome:
    """Raise or change a state through ``source``'s policy. ``execute`` skips the policy and the two-person rule:
    only for alarms already shown publicly (a bridge that issued it while the server was unreachable)."""
    target = State(target)
    if source == policy.SCHEDULE:
        drill = True
    if key:
        old = EvacRequest.objects.filter(event=event, key=key[:100]).first()
        if old is not None:
            return Outcome("duplicate", [], old)
    if target not in machine.ALARMS and source not in policy.PERSON_SOURCES:
        raise Refused("person_only", "Only people end alarms, with the all clear.")
    if check_perms and actor is not None:
        kind_drill = drill
        if target not in machine.ALARMS:
            kind_drill = next((r.drill for r in EvacState.objects.filter(
                event=event, zone=zone)), False)
        if not services.can(actor, event, target, drill=kind_drill, zone=zone, request=request):
            raise PermissionDenied("evacuation")
    services.check(event, target, zone=zone, drill=drill)  # refused changes are refused for every source
    now = timezone.now()
    states, seconds = two_person(event)
    user = actor if getattr(actor, "pk", None) else None
    base = {"event": event, "source": source, "state": target.value, "drill": drill, "zone": zone,
            "reason": reason[:300], "requested_by": user, "requested_repr": _who(actor, source), "created_at": now,
            "key": key[:100], "clear_zones": clear_zones}
    if source in policy.PERSON_SOURCES and user is not None and target.value in states and not execute:
        req = EvacRequest.objects.create(kind=policy.RequestKind.SECOND, deadline=now + timedelta(seconds=seconds),
                                         **base)
        _log(req, "evacuation.second_requested", user, request)
        _alert(event, req, _("Second person needed: %(s)s") % {"s": req.get_state_display()})
        return Outcome("waiting", [], req)
    decision = policy.resolve(rules(event), source, target.value, str(zone.pk) if zone else "") \
        if target in machine.ALARMS and not execute else policy.Decision(policy.Action.EXECUTE)
    if decision.action is policy.Action.EXECUTE:
        changes = services.change(event, target, zone=zone, drill=drill, actor=actor, request=request,
                                  source=source, reason=reason, clear_zones=clear_zones, check_perms=False)
        req = EvacRequest.objects.create(kind=policy.RequestKind.ARM, status=policy.Status.EXECUTED,
                                         decided_at=now, **base) if key else None
        return Outcome("executed", changes, req)
    if decision.action is policy.Action.ARM:
        dl = policy.deadline(policy.RequestKind.ARM, now, escalate_seconds=decision.escalate_seconds,
                             two_person_seconds=seconds)
        req = EvacRequest.objects.create(kind=policy.RequestKind.ARM, deadline=dl,
                                         escalate_seconds=decision.escalate_seconds, **base)
        _log(req, "evacuation.armed", user, request)
        _alert(event, req, _("Alarm to confirm (%(src)s): %(s)s") % {"src": source, "s": req.get_state_display()})
        return Outcome("armed", [], req)
    req = EvacRequest.objects.create(kind=policy.RequestKind.ARM, status=policy.Status.NOTIFIED, decided_at=now,
                                     **base)
    _log(req, "evacuation.notified", user, request)
    _alert(event, req, _("Alarm reported (%(src)s): %(s)s") % {"src": source, "s": req.get_state_display()},
           level="warn")
    return Outcome("notified", [], req)


def _log(req: EvacRequest, action: str, actor: Any, request: Any, **extra: Any) -> None:
    audit.log(action=action, actor=actor, event=req.event, target=req, request=request, drill=req.drill,
              message=f"{req.source}: {req.state}" + (f" in {req.zone.name}" if req.zone_id else ""),
              changes={"status": [None, req.status]}, scope={"source": req.source, **extra})


def _execute(req: EvacRequest, *, actor: Any, request: Any, status: str) -> list[StateChange]:
    note = req.reason
    by = req.requested_repr
    if by:
        note = (f"{note} · " if note else "") + f"requested by {by}"
    try:
        changes = services.change(req.event, req.state, zone=req.zone, drill=req.drill, actor=actor, request=request,
                                  source=req.source, reason=note, clear_zones=req.clear_zones, check_perms=False)
    except Refused:
        req.status = policy.Status.SUPERSEDED
        changes = []
    else:
        req.status = status
    req.decided_by = actor if getattr(actor, "pk", None) else None
    req.decided_at = timezone.now()
    req.save()
    return changes


def confirm(req: EvacRequest, *, actor: Any, request: Any = None) -> list[StateChange]:
    with transaction.atomic():
        req = EvacRequest.objects.select_for_update().get(pk=req.pk)
        if req.status != policy.Status.PENDING:
            raise Refused("decided", "This request was already decided.")
        if req.kind == policy.RequestKind.SECOND and req.requested_by_id == getattr(actor, "pk", None):
            raise Refused("same_person", "The second person must be someone else.")
        if not services.can(actor, req.event, State(req.state), drill=req.drill, zone=req.zone, request=request):
            raise PermissionDenied("evacuation")
        changes = _execute(req, actor=actor, request=request, status=policy.Status.CONFIRMED)
        _log(req, "evacuation.request_confirmed", actor, request, kind=req.kind)
    return changes


def reject(req: EvacRequest, *, actor: Any, request: Any = None) -> None:
    with transaction.atomic():
        req = EvacRequest.objects.select_for_update().get(pk=req.pk)
        if req.status != policy.Status.PENDING:
            raise Refused("decided", "This request was already decided.")
        own = req.requested_by_id is not None and req.requested_by_id == getattr(actor, "pk", None)
        if not own and not services.can(actor, req.event, State(req.state), drill=req.drill, zone=req.zone,
                                        request=request):
            raise PermissionDenied("evacuation")
        req.status, req.decided_by, req.decided_at = policy.Status.REJECTED, actor, timezone.now()
        req.save()
        _log(req, "evacuation.request_rejected", actor, request, kind=req.kind)


def process_due(event: Any = None, now: Any = None) -> int:
    """Escalate armed requests and expire two-person requests whose time is up; start due scheduled drills."""
    now = now or timezone.now()
    qs = EvacRequest.objects.filter(status=policy.Status.PENDING, deadline__lte=now)
    if event is not None:
        qs = qs.filter(event=event)
    done = 0
    for pk in list(qs.values_list("pk", flat=True)):
        with transaction.atomic():
            req = EvacRequest.objects.select_for_update().select_related("event", "zone").get(pk=pk)
            if req.status != policy.Status.PENDING:
                continue
            _two, seconds = two_person(req.event)
            what = policy.due(policy.RequestKind(req.kind), req.created_at, now,
                              escalate_seconds=req.escalate_seconds, two_person_seconds=seconds)
            if what is policy.Status.ESCALATED:
                _execute(req, actor=None, request=None, status=policy.Status.ESCALATED)
                _log(req, "evacuation.request_escalated", None, None)
                _alert(req.event, req, _("Alarm executed: nobody answered in time"))
            elif what is policy.Status.EXPIRED:
                req.status, req.decided_at = policy.Status.EXPIRED, now
                req.save()
                _log(req, "evacuation.request_expired", None, None)
                _alert(req.event, req, _("Not executed: no second person confirmed in time"))
            else:
                continue
            done += 1
    done += start_due_drills(event, now)
    from . import acks

    done += acks.watchdog(event, now)
    if event is None:
        from . import bridges

        done += bridges.sweep(now)
    return done


def start_due_drills(event: Any = None, now: Any = None) -> int:
    now = now or timezone.now()
    qs = ScheduledDrill.objects.filter(started_at__isnull=True, at__lte=now).select_related("event", "zone")
    if event is not None:
        qs = qs.filter(event=event)
    n = 0
    for drill in qs:
        drill.started_at = now
        if now - drill.at > DRILL_GRACE:
            drill.outcome = "missed (the server was not running at the planned time)"
        else:
            try:
                out = trigger(drill.event, drill.state, source=policy.SCHEDULE, zone=drill.zone, drill=True,
                              reason=drill.note or "Scheduled drill", check_perms=False)
            except Refused as err:
                drill.outcome = f"not started: {err.message}"
            else:
                drill.outcome = out.result
                n += 1
        drill.save()
    return n


def pending(event: Any) -> list[EvacRequest]:
    return list(EvacRequest.objects.filter(event=event, status=policy.Status.PENDING)
                .select_related("zone", "requested_by").order_by("created_at"))


# ------------------------------------------------------------------------------------------- configuration
def save_policy(event: Any, *, source: str, state: str, zone: Any, action: str, escalate_seconds: int | None,
                actor: Any = None, request: Any = None) -> EvacPolicy:
    row: EvacPolicy
    row, _created = EvacPolicy.objects.update_or_create(
        event=event, source=source, state=state, zone=zone,
        defaults={"action": action, "escalate_seconds": escalate_seconds if action == "arm" else None})
    audit.log(action="evacuation.policy_saved", actor=actor, event=event, target=row, request=request,
              message=str(row), changes={"action": [None, action], "escalate_seconds": [None, row.escalate_seconds]},
              scope={"source": source, "state": state, "zone": str(zone.pk) if zone else None})
    return row


def delete_policy(event: Any, pk: str, *, actor: Any = None, request: Any = None) -> None:
    row = EvacPolicy.objects.filter(event=event, pk=pk).first()
    if row is not None:
        audit.log(action="evacuation.policy_deleted", actor=actor, event=event, target=row, request=request,
                  message=str(row))
        row.delete()


def schedule_drill(event: Any, *, at: Any, state: str, zone: Any, note: str = "", actor: Any = None,
                   request: Any = None) -> ScheduledDrill:
    row: ScheduledDrill = ScheduledDrill.objects.create(event=event, at=at, state=state, zone=zone, note=note[:300],
                                        created_by=actor if getattr(actor, "pk", None) else None)
    audit.log(action="evacuation.drill_scheduled", actor=actor, event=event, target=row, request=request,
              message=str(row), drill=True)
    return row


def delete_drill(event: Any, pk: str, *, actor: Any = None, request: Any = None) -> None:
    row = ScheduledDrill.objects.filter(event=event, pk=pk, started_at__isnull=True).first()
    if row is not None:
        audit.log(action="evacuation.drill_unscheduled", actor=actor, event=event, target=row, request=request,
                  message=str(row), drill=True)
        row.delete()
