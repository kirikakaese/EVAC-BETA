# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every transition of the state machine (brief §8.7), plus properties of :func:`effective`."""
import itertools
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.evacuation import machine
from apps.evacuation.machine import ALARMS, SEVERITY, Kind, Refused, State, Status

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
NOW = T0 + timedelta(minutes=10)
ALL = list(State)


def status(state: State, drill: bool) -> Status:
    until = NOW + timedelta(minutes=3) if state is State.ALL_CLEAR else None
    return Status(state, drill and state is not State.NORMAL, T0, until)


def spec(before: Status, target: State, drill: bool, elsewhere: bool) -> str:
    """The rules of brief §8.2 and the 3.3 decisions, written out independently of the implementation."""
    if target is State.NORMAL:
        return {State.ALL_CLEAR: "end", State.NORMAL: "unchanged"}.get(before.state, "needs_all_clear")
    if target is State.ALL_CLEAR:
        return "clear" if before.state in ALARMS else "nothing_to_clear"
    if drill and ((before.state in ALARMS and not before.drill) or elsewhere):
        return "real_alarm_active"
    if before.state is target and before.drill == drill:
        return "unchanged"
    if before.state not in ALARMS:
        return "raise"
    if before.drill and not drill:
        return "replace_drill"
    return "escalate" if SEVERITY[target] > SEVERITY[before.state] else "step_down"


CASES = [(b, bd, t, d, e) for b, bd, t, d, e in itertools.product(ALL, (False, True), ALL, (False, True),
                                                                  (False, True))
         if not (b is State.NORMAL and bd)]


@pytest.mark.parametrize(("before", "before_drill", "target", "drill", "elsewhere"), CASES,
                         ids=lambda v: str(v.value if isinstance(v, State) else v))
def test_every_transition(before, before_drill, target, drill, elsewhere):
    b = status(before, before_drill)
    expected = spec(b, target, drill, elsewhere)
    if expected in {k.value for k in Kind}:
        change = machine.transition(b, target, drill=drill, now=NOW, clear_seconds=120,
                                    real_alarm_elsewhere=elsewhere)
        assert change.kind.value == expected and change.before == b
        after = change.after
        assert after.state is target and after.since == NOW
        if target is State.ALL_CLEAR:
            assert after.drill == b.drill and after.clear_until == NOW + timedelta(seconds=120)
        elif target is State.NORMAL:
            assert not after.drill and after.clear_until is None
        else:
            assert after.drill == drill and after.clear_until is None
    else:
        with pytest.raises(Refused) as err:
            machine.transition(b, target, drill=drill, now=NOW, real_alarm_elsewhere=elsewhere)
        assert err.value.code == expected and err.value.message


def test_case_count():
    # 11 reachable before-statuses x 6 targets x 2 drill x 2 elsewhere
    assert len(CASES) == 11 * 6 * 2 * 2


@pytest.mark.parametrize("target", [State.STAFF_ALERT, State.ATTENTION, State.SHELTER])
def test_disabled_states(target):
    enabled = frozenset(machine.ALWAYS_ENABLED)
    with pytest.raises(Refused) as err:
        machine.transition(machine.NORMAL, target, drill=False, now=NOW, enabled=enabled)
    assert err.value.code == "disabled"
    # evacuate, all clear and normal cannot be switched off
    raised = machine.transition(machine.NORMAL, State.EVACUATE, drill=False, now=NOW, enabled=enabled)
    cleared = machine.transition(raised.after, State.ALL_CLEAR, drill=False, now=NOW, enabled=enabled)
    assert machine.transition(cleared.after, State.NORMAL, drill=False, now=NOW, enabled=enabled).kind is Kind.END


def test_all_clear_display_time():
    s = Status(State.ALL_CLEAR, True, T0, T0 + timedelta(minutes=5))
    assert machine.current(s, T0 + timedelta(minutes=4)) == s
    after = machine.current(s, T0 + timedelta(minutes=5))
    assert after.state is State.NORMAL and not after.drill and after.since == T0 + timedelta(minutes=5)
    # an expired all clear behaves like normal: nothing to clear, can raise again
    with pytest.raises(Refused):
        machine.transition(s, State.NORMAL, drill=False, now=T0 + timedelta(hours=1))
    assert machine.transition(s, State.EVACUATE, drill=False, now=T0 + timedelta(hours=1)).kind is Kind.RAISE
    # zero minutes: straight back to normal
    zero = machine.transition(Status(State.EVACUATE, False, T0), State.ALL_CLEAR, drill=False, now=NOW,
                              clear_seconds=0)
    assert machine.current(zero.after, NOW).state is State.NORMAL


@given(st.sampled_from(sorted(ALARMS)), st.booleans(), st.integers(min_value=0, max_value=10 ** 9))
def test_never_auto_clear(state, drill, seconds):
    s = Status(state, drill, T0)
    assert machine.current(s, T0 + timedelta(seconds=seconds)) == s


def test_end_drill():
    assert machine.end_drill(Status(State.EVACUATE, False, T0), NOW) is None
    assert machine.end_drill(machine.NORMAL, NOW) is None
    ended = machine.end_drill(Status(State.ATTENTION, True, T0), NOW)
    assert ended is not None and ended.kind is Kind.DRILL_ENDED and ended.after == Status(State.NORMAL, False, NOW)
    assert machine.end_drill(Status(State.ALL_CLEAR, True, T0, NOW + timedelta(minutes=1)), NOW) is not None
    assert machine.end_drill(Status(State.ALL_CLEAR, True, T0, T0), NOW) is None  # already over


statuses = st.builds(Status, st.sampled_from(ALL), st.booleans(), st.just(T0),
                     st.sampled_from([None, T0 + timedelta(minutes=1), NOW + timedelta(minutes=5)]))


@given(st.lists(statuses, max_size=6))
def test_effective_properties(items):
    shown = machine.effective(items, NOW)
    cur = [machine.current(s, NOW) for s in items]
    real = [s for s in cur if s.real_alarm]
    if real:
        # a drill never masks a real alarm, and the most severe real alarm is shown
        assert not shown.drill and shown.severity == max(s.severity for s in real)
    else:
        assert shown.severity == max([s.severity for s in cur] + [0])
    assert shown in cur or shown == machine.NORMAL
    assert machine.effective(list(reversed(items)), NOW).severity == shown.severity


def test_effective_examples():
    ev = Status(State.ATTENTION, False, T0)
    zone = Status(State.EVACUATE, False, T0)
    assert machine.effective([ev, zone], NOW) is zone
    assert machine.effective([ev, machine.NORMAL], NOW) is ev
    assert machine.effective([], NOW) == machine.NORMAL
    drill = Status(State.EVACUATE, True, T0)
    assert machine.effective([drill, Status(State.STAFF_ALERT, False, T0)], NOW).state is State.STAFF_ALERT
    assert machine.effective([drill], NOW) is drill
    same_drill = Status(State.ATTENTION, True, T0)
    assert machine.effective([same_drill, ev], NOW) is ev and machine.effective([ev, same_drill], NOW) is ev
    clear = Status(State.ALL_CLEAR, False, T0, NOW + timedelta(minutes=1))
    assert machine.effective([clear, machine.NORMAL], NOW) is clear
