# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure permission evaluation, incl. property tests for scopes and two-factor rules."""
from hypothesis import given
from hypothesis import strategies as st

from apps.events.permissions import Access, Grant, Reason, build_access

ZONE_A = ("zone", "a")
VENUE = ("venue", "v")


def test_event_wide_grant():
    acc = build_access([Grant("orga", frozenset({"screens.control"}))], two_factor=False, sensitive=[])
    assert acc.allows("screens.control")
    assert acc.allows("screens.control", [VENUE, ZONE_A])
    assert acc.check("screens.view").reason is Reason.NO_GRANT


def test_scoped_grant():
    g = Grant("ctl", frozenset({"screens.control"}), scope_kind="zone", scope_id="a")
    acc = build_access([g], two_factor=False, sensitive=[])
    assert acc.allows("screens.control", [VENUE, ZONE_A])
    assert acc.check("screens.control", [VENUE, ("zone", "b")]).reason is Reason.OUT_OF_SCOPE
    assert acc.check("screens.control").reason is Reason.OUT_OF_SCOPE  # event-wide action needs event-wide grant
    assert acc.scopes_for("screens.control") == [ZONE_A]
    assert "screens.control" in acc.anywhere()


def test_two_factor_rules():
    roles = [Grant("security", frozenset({"evacuation.trigger", "ops.view"}), require_2fa=True),
             Grant("viewer", frozenset({"ops.view"}))]
    acc = build_access(roles, two_factor=False, sensitive=["evacuation.trigger"])
    assert acc.check("evacuation.trigger").reason is Reason.NEEDS_2FA
    assert acc.allows("ops.view")  # via the viewer role
    assert acc.blocked_roles() == ["security"]
    assert "evacuation.trigger" not in acc.anywhere()
    assert acc.scopes_for("evacuation.trigger") == []
    acc2 = build_access(roles, two_factor=True, sensitive=["evacuation.trigger"])
    assert acc2.allows("evacuation.trigger") and acc2.blocked_roles() == []
    assert acc2.scopes_for("evacuation.trigger") is None


def test_sensitive_permission_needs_2fa_even_without_role_flag():
    acc = build_access([Grant("admin", frozenset({"events.roles"}))], two_factor=False, sensitive=["events.roles"])
    assert acc.check("events.roles").reason is Reason.NEEDS_2FA


scope = st.tuples(st.sampled_from(["venue", "zone", "room"]), st.sampled_from(["1", "2", "3"]))


@given(st.lists(st.tuples(st.booleans(), scope, st.booleans()), max_size=5),
       st.lists(scope, max_size=4), st.booleans())
def test_never_allowed_without_matching_grant(grants, chain, two_factor):
    """Property: allowed <=> some grant holds the perm, covers the target, and 2FA rules pass."""
    built = [Grant(f"r{i}", frozenset({"x.do"}) if has else frozenset(), scope_kind=s[0] if scoped else "",
                   scope_id=s[1] if scoped else "", require_2fa=i % 2 == 0)
             for i, (has, s, scoped) in enumerate(grants)]
    acc = Access(tuple(built), two_factor, frozenset())
    expected = any("x.do" in g.permissions and g.covers(chain) and (two_factor or not g.require_2fa) for g in built)
    assert acc.allows("x.do", chain) == expected
