# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operator check-in (ADR-0052), off by default: while it is on (and the event is live, unless set otherwise) a
member of the check-in roles confirms “I'm here” every ``checkin_interval_minutes``.

When a check-in is due, the check-in roles get a reminder (step 0). Every ``checkin_grace_minutes`` after that
without a check-in, the next role of ``checkin_escalation`` is notified (steps 1, 2, …), in the app and, when set,
through ``checkin_channels`` (outbox). Each step runs once per missed check-in. A check-in ends the escalation and
tells the roles that were alerted.

Check-ins are counted where the event's live state is: on the venue node while it is checked out (central neither
takes them nor escalates). Nothing here touches evacuation or alarm states.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import webhooks
from apps.core.audit import log

from .models import CheckIn, CheckInEscalation, CheckInWatch
from .services import page_url, role_members, settings_of


@dataclass
class Status:
    enabled: bool
    active: bool
    interval: dt.timedelta
    grace: dt.timedelta
    last: CheckIn | None = None
    armed_at: dt.datetime | None = None
    due_at: dt.datetime | None = None
    overdue: bool = False
    #: escalation steps that already ran for the current due time
    steps: int = 0


def _active(event: Any, cfg: dict[str, Any]) -> bool:
    if not cfg.get("checkin_enabled"):
        return False
    if cfg.get("checkin_live_only", True):
        return bool(event.state == "live")
    return event.state in ("setup", "live", "teardown")


def _held_elsewhere(event: Any) -> bool:
    from apps.nodes import guard

    return guard.remote(event) or guard.read_only_copy(event)


def status(event: Any, now: dt.datetime | None = None) -> Status:
    now = now or timezone.now()
    cfg = settings_of(event)
    st = Status(enabled=bool(cfg.get("checkin_enabled")), active=_active(event, cfg),
                interval=dt.timedelta(minutes=int(cfg.get("checkin_interval_minutes", 30))),
                grace=dt.timedelta(minutes=int(cfg.get("checkin_grace_minutes", 5))))
    st.last = CheckIn.objects.filter(event=event).first()
    watch = CheckInWatch.objects.filter(event=event).first()
    st.armed_at = watch.armed_at if watch is not None else None
    if not st.active or st.armed_at is None:
        return st
    base = max(st.armed_at, st.last.at) if st.last is not None else st.armed_at
    st.due_at = base + st.interval
    st.overdue = now >= st.due_at
    st.steps = CheckInEscalation.objects.filter(event=event, due_at=st.due_at, step__gte=1).count()
    return st


def roles_of(cfg: dict[str, Any], key: str) -> list[str]:
    return [str(k).strip() for k in cfg.get(key) or [] if str(k).strip()]


def may_check_in(user: Any, event: Any, request: Any = None) -> bool:
    """Members of a check-in role, and people who manage the heartbeat."""
    from apps.events import rbac
    from apps.events.models import RoleAssignment

    if not getattr(user, "is_authenticated", False):
        return False
    if rbac.has_any(user, event, "heartbeat.manage", request=request):
        return True
    keys = roles_of(settings_of(event), "checkin_roles")
    return bool(keys) and RoleAssignment.objects.filter(role__event=event, role__key__in=keys,
                                                        membership__user=user).exists()


def _hhmm(event: Any, at: dt.datetime) -> str:
    return timezone.localtime(at, event.tz).strftime("%H:%M")


def check_in(event: Any, user: Any, *, request: Any = None, source: str = "page",
             now: dt.datetime | None = None) -> CheckIn:
    """“I'm here.” Raises ``PermissionDenied`` for people who may not check in, ``ValidationError`` while the event
    is held by a venue node (check in there)."""
    from apps.core.notify import notify

    if _held_elsewhere(event):
        raise ValidationError(_("This event is run by a venue node right now: check in there."))
    if not may_check_in(user, event, request):
        raise PermissionDenied("heartbeat check-in")
    now = now or timezone.now()
    before = status(event, now)
    ci = CheckIn.objects.create(event=event, user=user, user_repr=str(user)[:200], at=now, source=source[:20])
    if before.active and before.armed_at is None:
        CheckInWatch.objects.update_or_create(event=event, defaults={"armed_at": now})
    late = before.active and before.overdue
    if late and before.due_at is not None:
        alerted = CheckInEscalation.objects.filter(event=event, due_at=before.due_at, step__gte=1)
        keys = sorted({k for e in alerted for k in e.roles})
        if keys:
            notify([u for u in role_members(event, keys) if u.pk != user.pk],
                   _("Check-in received: %(u)s is at their post") % {"u": user},
                   body=_("Checked in at %(t)s.") % {"t": _hhmm(event, now)}, url=page_url(event), level="info",
                   event=event)
    log(action="heartbeat.checkin", actor=user, event=event, request=request,
        message=f"Check-in by {user}" + (" (late)" if late else ""), changes={"source": source, "late": late})
    payload = {"event": event.slug, "user": str(user), "at": now.isoformat(), "late": late, "source": source}
    transaction.on_commit(lambda: webhooks.emit("heartbeat.checked_in", payload, event=event))
    return ci


def escalate_due(event: Any, now: dt.datetime | None = None) -> int:
    """Beat task for one event: arm check-ins when they become active, then run the steps that are due. Returns how
    many steps ran."""
    now = now or timezone.now()
    cfg = settings_of(event)
    if not _active(event, cfg) or _held_elsewhere(event):
        CheckInWatch.objects.filter(event=event, armed_at__isnull=False).update(armed_at=None)
        return 0
    watch, _created = CheckInWatch.objects.get_or_create(event=event)
    if watch.armed_at is None:
        watch.armed_at = now  # from now on: the first check-in is due one interval later
        watch.save(update_fields=["armed_at"])
        return 0
    st = status(event, now)
    if st.due_at is None or now < st.due_at:
        return 0
    chain = roles_of(cfg, "checkin_escalation")
    fired = 0
    for step in range(len(chain) + 1):
        if now < st.due_at + step * st.grace:
            break
        roles = roles_of(cfg, "checkin_roles") if step == 0 else [chain[step - 1]]
        if _fire(event, st, step, roles, cfg, now):
            fired += 1
    return fired


def _fire(event: Any, st: Status, step: int, roles: list[str], cfg: dict[str, Any], now: dt.datetime) -> bool:
    from apps.core import alerts
    from apps.core.notify import notify
    from apps.core.plugins import Alert

    assert st.due_at is not None
    try:
        with transaction.atomic():
            esc = CheckInEscalation.objects.create(event=event, due_at=st.due_at, step=step, roles=roles, at=now)
    except IntegrityError:
        return False  # this step already ran
    since = _hhmm(event, st.last.at if st.last is not None else st.armed_at or st.due_at)
    who = ", ".join(roles_of(cfg, "checkin_roles")) or _("the control room")
    url = page_url(event)
    if step == 0:
        title, level = _("Check-in due: confirm you are at your post"), "warn"
        body = _("Last check-in: %(t)s. Press “I'm here” on the heartbeat page, the control room or the staff app.") \
            % {"t": since}
        keys: list[str] = []
    else:
        title, level = _("Missed check-in: nobody from %(r)s since %(t)s") % {"r": who, "t": since}, "err"
        body = _("Escalation step %(s)s: please check on the control room.") % {"s": step}
        keys = [str(c) for c in cfg.get("checkin_channels") or []]
    n = notify(role_members(event, roles), title, body=body, url=url, level=level, event=event)
    sent = alerts.enqueue(event, keys, Alert(title=title, body=body, level=level, url=url,
                                             key=f"checkin:{event.pk}:{st.due_at.isoformat()}:{step}")) if keys else 0
    esc.recipients = n
    esc.channels = [k for k in keys if k in alerts.channels(event)] if sent else []
    esc.save(update_fields=["recipients", "channels"])
    log(action="heartbeat.checkin_reminder" if step == 0 else "heartbeat.checkin_escalated", event=event,
        message=title[:500], changes={"step": step, "roles": roles, "recipients": n, "channels": sent,
                                      "due_at": st.due_at.isoformat()})
    if step > 0:
        payload = {"event": event.slug, "step": step, "roles": roles, "due_at": st.due_at.isoformat(),
                   "last_checkin": st.last.at.isoformat() if st.last is not None else None}
        transaction.on_commit(lambda: webhooks.emit("heartbeat.checkin_missed", payload, event=event))
    return True


def history(event: Any, limit: int = 10) -> list[CheckIn]:
    return list(CheckIn.objects.filter(event=event).select_related("user")[:limit])
