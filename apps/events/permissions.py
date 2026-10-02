# SPDX-License-Identifier: AGPL-3.0-or-later
"""Permission evaluation (pure functions, no database access).

A user's access within one event is a list of :class:`Grant` objects (one per role assignment). A grant
applies to an action when

* it contains the permission key,
* its scope is empty (event-wide) or the target lives in that scope (``(kind, id)`` in the target's
  scope chain), and
* two-factor requirements are met: roles with ``require_2fa`` and every ``sensitive`` permission need a
  two-factor verified session.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

ScopeRef = tuple[str, str]


class Reason(StrEnum):
    OK = "ok"
    NO_GRANT = "no_grant"
    OUT_OF_SCOPE = "out_of_scope"
    NEEDS_2FA = "needs_2fa"


@dataclass(frozen=True)
class Grant:
    role: str
    permissions: frozenset[str]
    scope_kind: str = ""
    scope_id: str = ""
    require_2fa: bool = False

    @property
    def scoped(self) -> bool:
        return bool(self.scope_kind)

    def covers(self, chain: Sequence[ScopeRef] | None) -> bool:
        """Does the grant's scope include a target with scope ``chain`` (None = event-wide action)?"""
        if not self.scoped:
            return True
        if chain is None:
            return False
        return (self.scope_kind, self.scope_id) in chain


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: Reason
    via: str = ""


@dataclass(frozen=True)
class Access:
    grants: tuple[Grant, ...] = ()
    two_factor: bool = False
    sensitive: frozenset[str] = field(default_factory=frozenset)

    def _usable(self, grant: Grant, perm: str) -> bool:
        if not self.two_factor and (grant.require_2fa or perm in self.sensitive):
            return False
        return perm in grant.permissions

    def check(self, perm: str, chain: Sequence[ScopeRef] | None = None) -> Decision:
        holders = [g for g in self.grants if perm in g.permissions]
        if not holders:
            return Decision(False, Reason.NO_GRANT)
        in_scope = [g for g in holders if g.covers(chain)]
        if not in_scope:
            return Decision(False, Reason.OUT_OF_SCOPE)
        for g in in_scope:
            if self._usable(g, perm):
                return Decision(True, Reason.OK, g.role)
        return Decision(False, Reason.NEEDS_2FA)

    def allows(self, perm: str, chain: Sequence[ScopeRef] | None = None) -> bool:
        return self.check(perm, chain).allowed

    def anywhere(self) -> frozenset[str]:
        """Permissions usable in at least one scope (navigation, list pages)."""
        out: set[str] = set()
        for g in self.grants:
            out.update(p for p in g.permissions if self._usable(g, p))
        return frozenset(out)

    def scopes_for(self, perm: str) -> list[ScopeRef] | None:
        """``None`` = allowed event-wide; otherwise the scopes the permission is limited to (maybe empty)."""
        scopes: list[ScopeRef] = []
        for g in self.grants:
            if not self._usable(g, perm):
                continue
            if not g.scoped:
                return None
            scopes.append((g.scope_kind, g.scope_id))
        return scopes

    def blocked_roles(self) -> list[str]:
        """Roles that would grant something but are inactive for lack of two-factor authentication."""
        if self.two_factor:
            return []
        return sorted({g.role for g in self.grants if g.require_2fa})


def build_access(grants: Iterable[Grant], *, two_factor: bool, sensitive: Iterable[str]) -> Access:
    return Access(tuple(grants), two_factor, frozenset(sensitive))
