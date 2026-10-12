# SPDX-License-Identifier: AGPL-3.0-or-later
"""The health monitor (ADR-0052): runs the health checks modules registered with ``r.health_check``, keeps the
confirmed status of every item, and reports changes into and out of "down".

* A check of a module that is off (for the event, or instance-wide) is skipped. A check that raises shows as
  ``unknown`` and never alerts.
* A change into or out of ``down`` is confirmed only when the observed status stayed the same for the grace period
  (``heartbeat.grace_seconds``): a link that flaps does not alert on every blip, and a short outage does not alert at
  all. Changes between ``ok``, ``warn`` and ``unknown`` are taken at once and never alert.
* A confirmed ``down`` (while the event is in one of ``alert_states``) notifies the members of ``notify_roles`` in
  the app (and by Web Push), queues staff alerts for ``alert_channels`` through the outbox, writes the audit log and
  emits ``heartbeat.down`` (the ops log turns it into a line for the control room). Its recovery is reported the
  same way (``heartbeat.recovered``).

Nothing here changes any evacuation or alarm state: the monitor only reads and reports.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import modules, settings_store, webhooks
from apps.core.audit import log
from apps.core.plugins import HEALTH_STATUSES, HealthCheckSpec, HealthItem
from apps.core.registry import registry

from .models import HealthState

MODULE = "heartbeat"
logger = logging.getLogger("evac.heartbeat")
#: shown first: the worst status
RANK = {"down": 3, "warn": 2, "unknown": 1, "ok": 0}


def settings_of(event: Any) -> dict[str, Any]:
    return settings_store.get("heartbeat", event=event) if event is not None else settings_store.get("heartbeat")


# ------------------------------------------------------------------ running checks
def specs_for(event: Any) -> list[HealthCheckSpec]:
    """The checks that apply to ``event`` (None: the instance-wide view)."""
    from apps.nodes import guard

    remote = event is not None and guard.remote(event)
    out = []
    for spec in sorted(registry.ensure_loaded().health_checks.values(), key=lambda s: (s.order, s.key)):
        if (event is None and spec.scope == "event") or (event is not None and spec.scope == "instance"):
            continue
        if spec.module != "core" and not modules.is_enabled(spec.module, event):
            continue
        if remote and not spec.while_checked_out:
            continue
        out.append(spec)
    return out


def normalise(value: Any, spec: HealthCheckSpec) -> HealthItem:
    """A check may return ``HealthItem`` objects or plain dicts; unknown statuses become ``unknown``."""
    if isinstance(value, HealthItem):
        item = value
    elif isinstance(value, Mapping):
        item = HealthItem(key=str(value.get("key") or spec.key), label=str(value.get("label") or spec.name),
                          status=value.get("status", "unknown"), detail=str(value.get("detail") or ""),
                          since=value.get("since"), url=str(value.get("url") or ""))
    else:
        raise TypeError(f"health check {spec.key} returned {type(value).__name__}")
    status = item.status if item.status in HEALTH_STATUSES else "unknown"
    return HealthItem(key=str(item.key)[:200] or spec.key, label=str(item.label)[:200], status=status,
                      detail=str(item.detail or "")[:500], since=item.since, url=str(item.url or "")[:500])


@dataclass
class Observation:
    spec: HealthCheckSpec
    item: HealthItem
    state: HealthState | None = None

    @property
    def rank(self) -> int:
        return RANK.get(self.item.status, 0)


def observe(event: Any) -> list[Observation]:
    """Run every applicable check now (database reads only)."""
    out: list[Observation] = []
    for spec in specs_for(event):
        try:
            items = [normalise(v, spec) for v in spec.check(event)]
        except Exception as exc:  # a broken check must not stop the others
            logger.exception("health check %s failed", spec.key)
            items = [HealthItem(key=spec.key, label=spec.name, status="unknown",
                                detail=_("The check failed: %(e)s") % {"e": type(exc).__name__})]
        out.extend(Observation(spec, item) for item in items)
    return out


def _states(event: Any) -> Any:
    return HealthState.objects.filter(event=event) if event is not None else HealthState.objects.filter(
        event__isnull=True)


def overview(event: Any) -> dict[str, Any]:
    """What the heartbeat page and the control room panel show: every item now, with its confirmed status since."""
    obs = observe(event)
    states = {(s.check_key, s.item): s for s in _states(event)}
    for o in obs:
        o.state = states.get((o.spec.key, o.item.key))
    counts = {k: 0 for k in RANK}
    for o in obs:
        counts[o.item.status] += 1
    worst = max((o.item.status for o in obs), key=lambda s: RANK[s], default="ok")
    groups: list[dict[str, Any]] = []
    for o in obs:
        if not groups or groups[-1]["spec"].key != o.spec.key:
            groups.append({"spec": o.spec, "items": []})
        groups[-1]["items"].append(o)
    return {"observations": obs, "groups": groups, "counts": counts, "worst": worst,
            "problems": sorted([o for o in obs if o.item.status in ("down", "warn")], key=lambda o: -o.rank)}


# ------------------------------------------------------------------ status changes
@dataclass
class Change:
    spec: HealthCheckSpec
    item: HealthItem
    state: HealthState
    old: str
    new: str
    old_since: dt.datetime | None = None


def _graced(old: str, new: str) -> bool:
    return "down" in (old, new)


def evaluate(event: Any, now: dt.datetime | None = None) -> list[Change]:
    """Observe ``event`` (None: instance-wide), confirm status changes after the grace period and report them.
    Returns the confirmed changes."""
    now = now or timezone.now()
    cfg = settings_of(event)
    grace = dt.timedelta(seconds=int(cfg.get("grace_seconds", 60)))
    existing = {(s.check_key, s.item): s for s in _states(event)}
    seen: set[tuple[str, str]] = set()
    changes: list[Change] = []
    for o in observe(event):
        key = (o.spec.key, o.item.key)
        if key in seen:
            continue
        seen.add(key)
        st = existing.get(key)
        if st is None:
            # first sight: a problem that is already there alerts after the grace period like any other
            st = HealthState(event=event, check_key=o.spec.key, item=o.item.key, since=now, checked_at=now,
                             status="unknown" if o.item.status == "down" else o.item.status)
            if o.item.status == "down":
                st.candidate, st.candidate_since = "down", now
        st.label, st.detail, st.url, st.checked_at = o.item.label, o.item.detail, o.item.url, now
        new = o.item.status
        if new == st.status:
            st.candidate, st.candidate_since = "", None
        elif st.candidate != new:
            st.candidate, st.candidate_since = new, now
        if st.candidate and st.candidate_since is not None and (
                not _graced(st.status, st.candidate) or now - st.candidate_since >= grace):
            old, old_since = st.status, st.since
            st.status, st.since = st.candidate, st.candidate_since
            st.candidate, st.candidate_since = "", None
            changes.append(Change(o.spec, o.item, st, old, st.status, old_since))
        st.save()
    gone = [s.pk for k, s in existing.items() if k not in seen]
    if gone:  # the item disappeared (deleted, module switched off): nothing left to watch
        HealthState.objects.filter(pk__in=gone).delete()
    alerting = event is None or event.state in (cfg.get("alert_states") or [])
    for down, picked in ((True, [c for c in changes if c.new == "down" and alerting]),
                         (False, [c for c in changes if c.old == "down" and c.state.alerted])):
        by_check: dict[str, list[Change]] = {}
        for c in picked:
            by_check.setdefault(c.spec.key, []).append(c)
        for group in by_check.values():
            _report(event, group, down=down, now=now)
    return changes


def page_url(event: Any) -> str:
    return reverse("heartbeat:index", args=[event.slug]) if event is not None else reverse("heartbeat_admin:index")


def _recipients(event: Any, role_keys: list[str]) -> list[Any]:
    if event is None:
        from apps.accounts.models import User

        return list(User.objects.filter(is_superuser=True, is_active=True))
    return role_members(event, role_keys)


def role_members(event: Any, role_keys: list[str]) -> list[Any]:
    """Active members of the event holding one of the roles named by key."""
    from apps.events.models import RoleAssignment

    keys = [k.strip() for k in role_keys if str(k).strip()]
    if not keys:
        return []
    users = {a.membership.user for a in RoleAssignment.objects.filter(role__event=event, role__key__in=keys)
             .select_related("membership__user")}
    return sorted((u for u in users if u.is_active), key=lambda u: str(u.pk))


def payload_of(event: Any, c: Change) -> dict[str, Any]:
    return {"event": event.slug if event is not None else None, "check": c.spec.key, "check_name": c.spec.name,
            "item": c.item.key, "label": c.item.label, "status": c.new, "previous": c.old, "detail": c.item.detail,
            "since": c.state.since.isoformat() if c.state.since else None, "url": c.item.url}


#: more changes of one check at once are reported in one message (a power cut takes many screens down)
GROUP_AFTER = 3


def _report(event: Any, changes: list[Change], *, down: bool, now: dt.datetime) -> None:
    from apps.core import alerts
    from apps.core.notify import notify
    from apps.core.plugins import Alert

    cfg = settings_of(event)
    spec = changes[0].spec
    for c in changes:
        c.state.alerted = down
        c.state.save(update_fields=["alerted"])
    if len(changes) > GROUP_AFTER:
        labels = ", ".join(c.item.label for c in changes[:8]) + (" …" if len(changes) > 8 else "")
        title = (_("Down: %(n)s × %(c)s") if down else _("Back up: %(n)s × %(c)s")) % {"n": len(changes),
                                                                                    "c": spec.name}
        body, level = labels, "err" if down else "info"
    else:
        names = ", ".join(c.item.label if c.item.label == spec.name else f"{spec.name}: {c.item.label}"
                          for c in changes)
        if down:
            title, level = _("Down: %(n)s") % {"n": names}, "err"
            body = " ".join(c.item.detail for c in changes if c.item.detail)
        else:
            title, level = _("Back up: %(n)s") % {"n": names}, "info"
            c = changes[0]
            minutes = max(1, round((c.state.since - c.old_since).total_seconds() / 60)) if c.old_since else 0
            body = _("It was down for about %(m)s min.") % {"m": minutes} if minutes and len(changes) == 1 else ""
    url = page_url(event)
    n = notify(_recipients(event, list(cfg.get("notify_roles") or [])), title[:200], body=body[:1000], url=url,
               level=level, event=event)
    sent = 0
    if event is not None:
        sent = alerts.enqueue(event, [str(k) for k in cfg.get("alert_channels") or []], Alert(
            title=title[:200], body=body[:1000], level=level, url=url,
            key=f"heartbeat:{spec.key}:{changes[0].state.pk}:{'down' if down else 'up'}:{now.isoformat()}"))
    kind = "heartbeat.down" if down else "heartbeat.recovered"
    log(action=kind, event=event, message=title[:500], changes={
        "check": spec.key, "items": [c.item.key for c in changes][:50], "notified": n, "channels": sent})
    payloads = [payload_of(event, c) for c in changes]

    def emit() -> None:
        for p in payloads:
            webhooks.emit(kind, p, event=event)
    transaction.on_commit(emit)


def evaluate_all(now: dt.datetime | None = None) -> int:
    """Beat task: the instance-wide view and every event that is not archived and has the module on."""
    from apps.events.models import Event

    n = 0
    if modules.is_enabled(MODULE):
        n += len(evaluate(None, now))
    for event in Event.objects.exclude(state=Event.State.ARCHIVED):
        if modules.is_enabled(MODULE, event):
            n += len(evaluate(event, now))
    return n
