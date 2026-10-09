# SPDX-License-Identifier: AGPL-3.0-or-later
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core import hashchain


def build(payloads):
    rows, prev = [], hashchain.GENESIS
    for i, p in enumerate(payloads):
        h = hashchain.compute(prev, p)
        rows.append((i, prev, h, p))
        prev = h
    return rows


payload = st.dictionaries(st.text(min_size=1, max_size=5), st.one_of(st.integers(), st.text(max_size=10)), max_size=4)


@settings(deadline=None)  # pure CPU work; a busy CI runner must not turn timing into failures
@given(st.lists(payload, max_size=8))
def test_valid_chain_verifies(payloads):
    assert hashchain.verify(build(payloads)).ok


@settings(deadline=None)  # pure CPU work; a busy CI runner must not turn timing into failures
@given(st.lists(payload, min_size=2, max_size=8), st.data())
def test_any_modification_is_detected(payloads, data):
    rows = build(payloads)
    i = data.draw(st.integers(0, len(rows) - 1))
    rid, prev, h, p = rows[i]
    rows[i] = (rid, prev, h, {**p, "__tampered__": 1})
    result = hashchain.verify(rows)
    assert not result.ok and result.first_bad_id == rid


@settings(deadline=None)  # pure CPU work; a busy CI runner must not turn timing into failures
@given(st.lists(payload, min_size=3, max_size=8), st.data())
def test_removal_is_detected(payloads, data):
    rows = build(payloads)
    i = data.draw(st.integers(0, len(rows) - 2))
    del rows[i]
    assert not hashchain.verify(rows).ok


def test_reorder_is_detected():
    rows = build([{"a": 1}, {"a": 2}, {"a": 3}])
    rows[0], rows[1] = rows[1], rows[0]
    assert not hashchain.verify(rows).ok


def test_canonical_is_key_order_independent():
    assert hashchain.canonical({"b": 1, "a": [1, 2]}) == hashchain.canonical({"a": [1, 2], "b": 1})
