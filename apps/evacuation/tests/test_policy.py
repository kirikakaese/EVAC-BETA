# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trigger policy resolution and request timing (ADR-0031)."""
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.evacuation import policy
from apps.evacuation.policy import Action, Rule, Status

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def test_defaults():
    assert policy.resolve([], "web", "evacuate") == policy.Decision(Action.EXECUTE)
    assert policy.resolve([], "panic", "attention").action is Action.EXECUTE
    assert policy.resolve([], "schedule", "evacuate").action is Action.EXECUTE
    for src in ("api", "bridge", "dial"):
        d = policy.resolve([], src, "evacuate")
        assert d.action is Action.ARM and d.escalate_seconds == 120 and d.rule is None


def test_most_specific_rule_wins():
    rules = [Rule("api", Action.NOTIFY), Rule("api", Action.EXECUTE, state="evacuate"),
             Rule("api", Action.ARM, zone="z1", escalate_seconds=30),
             Rule("api", Action.ARM, state="evacuate", zone="z1", escalate_seconds=None),
             Rule("web", Action.ARM)]
    assert policy.resolve(rules, "api", "attention").action is Action.NOTIFY
    assert policy.resolve(rules, "api", "evacuate").action is Action.EXECUTE
    assert policy.resolve(rules, "api", "attention", "z1") == policy.Decision(Action.ARM, 30, rules[2])
    d = policy.resolve(rules, "api", "evacuate", "z1")
    assert d.action is Action.ARM and d.escalate_seconds is None
    assert policy.resolve(rules, "web", "evacuate").action is Action.ARM
    assert policy.resolve(rules, "bridge", "evacuate").action is Action.ARM  # untouched default
    # execute/notify never carry an escalation time
    assert policy.resolve([Rule("api", Action.EXECUTE, escalate_seconds=5)], "api", "x").escalate_seconds is None


@given(st.lists(st.builds(Rule, st.sampled_from(["api", "web"]), st.sampled_from(list(Action)),
                          st.sampled_from(["", "evacuate", "attention"]), st.sampled_from(["", "z1", "z2"]),
                          st.sampled_from([None, 30, 120])),
                max_size=8),
       st.sampled_from(["api", "web"]), st.sampled_from(["evacuate", "attention"]), st.sampled_from(["", "z1"]))
def test_resolution_is_order_independent_and_matching(rules, source, state, zone):
    d = policy.resolve(rules, source, state, zone)
    rev = policy.resolve(list(reversed(rules)), source, state, zone)
    assert d == rev
    if d.rule is not None:
        assert d.rule.source == source and d.rule.state in ("", state) and d.rule.zone in ("", zone)


def test_due_and_deadline():
    arm, second = policy.RequestKind.ARM, policy.RequestKind.SECOND
    assert policy.due(arm, T0, T0 + timedelta(seconds=119), escalate_seconds=120, two_person_seconds=60) is None
    assert policy.due(arm, T0, T0 + timedelta(seconds=120), escalate_seconds=120,
                      two_person_seconds=60) is Status.ESCALATED
    assert policy.due(arm, T0, T0 + timedelta(days=9), escalate_seconds=None, two_person_seconds=60) is None
    assert policy.due(second, T0, T0 + timedelta(seconds=59), escalate_seconds=None, two_person_seconds=60) is None
    assert policy.due(second, T0, T0 + timedelta(seconds=60), escalate_seconds=5,
                      two_person_seconds=60) is Status.EXPIRED  # a second-person request never executes itself
    assert policy.deadline(arm, T0, escalate_seconds=None, two_person_seconds=60) is None
    assert policy.deadline(arm, T0, escalate_seconds=10, two_person_seconds=60) == T0 + timedelta(seconds=10)
    assert policy.deadline(second, T0, escalate_seconds=10, two_person_seconds=60) == T0 + timedelta(seconds=60)


@pytest.mark.parametrize("kind", list(policy.RequestKind))
def test_never_escalates_a_second_person_request(kind):
    for s in range(0, 600, 7):
        got = policy.due(kind, T0, T0 + timedelta(seconds=s), escalate_seconds=1, two_person_seconds=60)
        if kind is policy.RequestKind.SECOND:
            assert got in (None, Status.EXPIRED)
