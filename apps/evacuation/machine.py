# SPDX-License-Identifier: AGPL-3.0-or-later
"""The evacuation state machine (brief §8.2, ADR-0029). Pure Python, no Django, mypy strict.

Every event has one status and every zone may have its own. A status is a state, a drill flag, when it began and,
for ``all_clear``, when the all-clear display ends. The rules:

- **Never auto-clear**: nothing returns to ``normal`` by timeout, reconnect or restart. Only an explicit
  ``all_clear`` by an authorised person ends an alarm; the all-clear display then runs for the configured time and
  turns into ``normal`` (computed on read, so a restart cannot shorten or lengthen it).
- Alarms may be raised, changed and stepped down directly (``evacuate`` -> ``shelter_in_place``), but ``normal`` is
  only reached through ``all_clear``.
- **Drills** run in any alarm state. A real alarm replaces a drill in the same scope at once; a drill cannot start
  while a real alarm is active, and a drill never masks a real alarm (:func:`effective`).
- **Highest severity wins** between the event status and the zone statuses that apply to a screen.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class State(StrEnum):
    NORMAL = "normal"
    STAFF_ALERT = "staff_alert"
    ATTENTION = "attention"
    SHELTER = "shelter_in_place"
    EVACUATE = "evacuate"
    ALL_CLEAR = "all_clear"


SEVERITY: dict[State, int] = {
    State.NORMAL: 0, State.ALL_CLEAR: 1, State.STAFF_ALERT: 2, State.ATTENTION: 3, State.SHELTER: 4,
    State.EVACUATE: 5,
}
ALARMS: frozenset[State] = frozenset({State.STAFF_ALERT, State.ATTENTION, State.SHELTER, State.EVACUATE})
#: states an event cannot switch off
ALWAYS_ENABLED: frozenset[State] = frozenset({State.NORMAL, State.ALL_CLEAR, State.EVACUATE})


class Kind(StrEnum):
    """What a change does; kept in the history and the audit log."""

    RAISE = "raise"  # normal / all clear -> alarm
    ESCALATE = "escalate"  # alarm -> more severe alarm
    STEP_DOWN = "step_down"  # alarm -> less severe alarm
    REPLACE_DRILL = "replace_drill"  # a real alarm takes over from a drill
    CLEAR = "clear"  # alarm -> all clear
    END = "end"  # all clear -> normal (early)
    DRILL_ENDED = "drill_ended"  # a drill elsewhere ended by a real alarm


class Refused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Status:
    state: State = State.NORMAL
    drill: bool = False
    since: datetime | None = None
    clear_until: datetime | None = None

    @property
    def alarm(self) -> bool:
        return self.state in ALARMS

    @property
    def real_alarm(self) -> bool:
        return self.alarm and not self.drill

    @property
    def severity(self) -> int:
        return SEVERITY[self.state]


NORMAL = Status()


def current(status: Status, now: datetime) -> Status:
    """The status as it is at ``now``: an all-clear whose display time is over is ``normal``."""
    if status.state is State.ALL_CLEAR and status.clear_until is not None and now >= status.clear_until:
        return Status(State.NORMAL, False, status.clear_until, None)
    return status


@dataclass(frozen=True)
class Change:
    before: Status
    after: Status
    kind: Kind


def transition(status: Status, target: State, *, drill: bool, now: datetime,
               enabled: frozenset[State] = frozenset(State), clear_seconds: int = 300,
               real_alarm_elsewhere: bool = False) -> Change:
    """Validate and apply one change requested by a person or a trigger. Raises :class:`Refused`.

    ``drill`` is the kind of alarm requested (ignored for ``all_clear``/``normal``, which keep the current kind).
    ``real_alarm_elsewhere``: a real alarm is active in another scope of the same event (no drill may start).
    """
    before = current(status, now)
    if target not in enabled and target not in ALWAYS_ENABLED:
        raise Refused("disabled", f"The state {target.value} is switched off for this event.")
    if target is State.NORMAL:
        if before.state is State.ALL_CLEAR:
            return Change(before, Status(State.NORMAL, False, now, None), Kind.END)
        if before.state is State.NORMAL:
            raise Refused("unchanged", "Already normal.")
        raise Refused("needs_all_clear", "Only the all clear ends an alarm.")
    if target is State.ALL_CLEAR:
        if not before.alarm:
            raise Refused("nothing_to_clear", "There is no alarm to clear.")
        until = now + timedelta(seconds=max(clear_seconds, 0))
        return Change(before, Status(State.ALL_CLEAR, before.drill, now, until), Kind.CLEAR)
    # an alarm state
    if drill and (before.real_alarm or real_alarm_elsewhere):
        raise Refused("real_alarm_active", "A real alarm is active; drills cannot start now.")
    if before.state is target and before.drill == drill:
        raise Refused("unchanged", "This state is already active.")
    after = Status(target, drill, now, None)
    if not before.alarm:
        kind = Kind.RAISE
    elif before.drill and not drill:
        kind = Kind.REPLACE_DRILL
    elif SEVERITY[target] > before.severity:
        kind = Kind.ESCALATE
    elif SEVERITY[target] < before.severity:
        kind = Kind.STEP_DOWN
    else:  # same state, real -> drill is refused above, so this is unreachable
        raise Refused("unchanged", "This state is already active.")  # pragma: no cover
    return Change(before, after, kind)


def end_drill(status: Status, now: datetime) -> Change | None:
    """A real alarm elsewhere in the event ends this scope's drill (alarm or drill all-clear)."""
    before = current(status, now)
    if not before.drill or before.state is State.NORMAL:
        return None
    return Change(before, Status(State.NORMAL, False, now, None), Kind.DRILL_ENDED)


def _rank(s: Status) -> tuple[int, int]:
    return s.severity, 0 if s.drill else 1


def effective(statuses: Iterable[Status], now: datetime) -> Status:
    """What a screen shows given the event status and the statuses of its zones: highest severity wins, real
    beats drill at the same severity, and while any real alarm applies drills are ignored altogether."""
    cur = [current(s, now) for s in statuses]
    if any(s.real_alarm for s in cur):
        cur = [s for s in cur if not s.drill]
    best = NORMAL
    for s in cur:
        if _rank(s) > _rank(best):
            best = s
    return best
