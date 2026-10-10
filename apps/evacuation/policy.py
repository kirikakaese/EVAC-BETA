# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trigger policies (brief §8.3, ADR-0031). Pure Python, mypy strict.

Every trigger source has a policy per stage and zone:

- ``execute``: switch at once (the source already had a person confirm, e.g. hold-to-confirm);
- ``arm``: raise an alarm request the control room confirms or rejects; with auto-escalation it executes when
  nobody answers in time (fail towards alarm: an unattended control room must not swallow a real alarm);
- ``notify``: only tell the control room.

The most specific rule wins: source + stage + zone, then source + stage, then source + zone, then source, then the
built-in default of the source. The **two-person rule** is per stage: a person's change into that stage waits
until a second authorised person confirms; when nobody does in time the request expires and nothing changes.
Policies never apply to ending an alarm: only people end alarms, and only with the all clear.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class Action(StrEnum):
    EXECUTE = "execute"
    ARM = "arm"
    NOTIFY = "notify"


#: built-in sources; extensions add theirs with ``EvacTriggerSpec`` (default ``arm``)
WEB, PANIC, API, BRIDGE, SCHEDULE = "web", "panic", "api", "bridge", "schedule"
#: sources where a person confirmed on the spot (hold-to-confirm); only they can be subject to the two-person rule
PERSON_SOURCES = frozenset({WEB, PANIC})
DEFAULTS: dict[str, Action] = {WEB: Action.EXECUTE, PANIC: Action.EXECUTE, API: Action.ARM, BRIDGE: Action.ARM,
                               SCHEDULE: Action.EXECUTE}
DEFAULT_ESCALATE = 120
DEFAULT_TWO_PERSON = 60


@dataclass(frozen=True)
class Rule:
    source: str
    action: Action
    state: str = ""  # "" = every stage
    zone: str = ""  # "" = every zone and the whole event
    escalate_seconds: int | None = DEFAULT_ESCALATE  # arm only; None = wait for a person


@dataclass(frozen=True)
class Decision:
    action: Action
    escalate_seconds: int | None = None
    rule: Rule | None = None


#: on equally specific rules the one leading more surely to an alarm wins (fail towards alarm)
_FIRMNESS = {Action.EXECUTE: 2, Action.ARM: 1, Action.NOTIFY: 0}


def resolve(rules: Iterable[Rule], source: str, state: str, zone: str = "") -> Decision:
    best: tuple[int, int, int, int, Rule] | None = None
    for r in rules:
        if r.source != source or r.state not in ("", state) or r.zone not in ("", zone):
            continue
        rank = (2 if r.state else 0) + (1 if r.zone else 0)
        # among equals: firmer action, then a shorter (or any) escalation
        esc = -(r.escalate_seconds if r.escalate_seconds is not None else 10 ** 9)
        # last: any total order, so the chosen rule never depends on the order of the rules
        tie = -(r.escalate_seconds if r.escalate_seconds is not None else -1)
        key = (rank, _FIRMNESS[r.action], esc if r.action is Action.ARM else 0, tie, r)
        if best is None or key[:4] > best[:4]:
            best = key
    if best is not None:
        r = best[4]
        return Decision(r.action, r.escalate_seconds if r.action is Action.ARM else None, r)
    action = DEFAULTS.get(source, Action.ARM)
    return Decision(action, DEFAULT_ESCALATE if action is Action.ARM else None)


class Status(StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"  # executed at once (kept for idempotent API deliveries and the history)
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"
    NOTIFIED = "notified"
    SUPERSEDED = "superseded"  # an equal or more severe alarm was set meanwhile


class RequestKind(StrEnum):
    ARM = "arm"  # a trigger waits for the control room
    SECOND = "second"  # a person waits for a second person


def due(kind: RequestKind, created: datetime, now: datetime, *, escalate_seconds: int | None,
        two_person_seconds: int) -> Status | None:
    """What happens to a pending request at ``now``: ``ESCALATED`` (execute), ``EXPIRED`` (drop), or None (wait)."""
    if kind is RequestKind.SECOND:
        return Status.EXPIRED if now >= created + timedelta(seconds=two_person_seconds) else None
    if escalate_seconds is None:
        return None
    return Status.ESCALATED if now >= created + timedelta(seconds=escalate_seconds) else None


def deadline(kind: RequestKind, created: datetime, *, escalate_seconds: int | None,
             two_person_seconds: int) -> datetime | None:
    if kind is RequestKind.SECOND:
        return created + timedelta(seconds=two_person_seconds)
    return None if escalate_seconds is None else created + timedelta(seconds=escalate_seconds)
