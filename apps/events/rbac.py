# SPDX-License-Identifier: AGPL-3.0-or-later
"""Role-based access control within an event (database-facing side of :mod:`.permissions`).

    from apps.events import rbac
    rbac.has_perm(request.user, event, "venues.manage", obj=zone, request=request)
    rbac.require(request, event, "events.members")            # raises PermissionDenied

Instance admins (superusers) hold an implicit event-wide ``admin`` grant everywhere. Results are cached
on the request object for the duration of the request.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied

from apps.core.registry import registry

from .permissions import Access, Grant, ScopeRef, build_access


@dataclass
class Effective:
    access: Access
    member: bool
    permissions: frozenset[str] = field(default_factory=frozenset)
    blocked_roles: list[str] = field(default_factory=list)


def _two_factor(request, user) -> bool:
    if request is None:
        return False
    token = getattr(request, "service_token", None)
    if token is not None:
        return bool(token.created_with_2fa)
    from apps.accounts.twofactor import is_verified

    return is_verified(request)


def grants_for(user, event) -> tuple[list[Grant], bool]:
    from .models import RoleAssignment

    grants: list[Grant] = []
    rows = list(RoleAssignment.objects.filter(membership__event=event, membership__user=user)
                .select_related("role"))
    member = bool(rows) or event.memberships.filter(user=user).exists()
    for ra in rows:
        grants.append(Grant(role=ra.role.name, permissions=frozenset(ra.role.expanded()), scope_kind=ra.scope_kind,
                            scope_id=ra.scope_id, require_2fa=ra.role.require_2fa))
    if user.is_superuser:
        grants.append(Grant(role="Instance admin", permissions=frozenset(registry.permission_keys())))
        member = True
    return grants, member


def effective(user, event, *, request=None, two_factor: bool | None = None) -> Effective:
    cache_key = (event.pk, two_factor)
    cache = getattr(request, "_evac_rbac", None) if request is not None else None
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        result = Effective(Access(), member=False)
    else:
        grants, member = grants_for(user, event)
        tf = _two_factor(request, user) if two_factor is None else two_factor
        access = build_access(grants, two_factor=tf, sensitive=registry.sensitive_permissions())
        token = getattr(request, "service_token", None) if request is not None else None
        if token is not None and token.event_id and token.event_id != event.pk:
            access, member = Access(), False
        result = Effective(access, member, access.anywhere(), access.blocked_roles())
    if request is not None:
        if cache is None:
            cache = {}
            request._evac_rbac = cache
        cache[cache_key] = result
    return result


def scope_chain(obj) -> list[ScopeRef] | None:
    """Scopes an object lives in. Objects provide ``evac_scope_chain()``; None = event-wide target."""
    if obj is None:
        return None
    fn = getattr(obj, "evac_scope_chain", None)
    return list(fn()) if callable(fn) else None


def has_perm(user, event, perm: str, *, obj=None, scope: list[ScopeRef] | None = None, request=None) -> bool:
    chain = scope if scope is not None else scope_chain(obj)
    return effective(user, event, request=request).access.allows(perm, chain)


def has_any(user, event, perm: str, *, request=None) -> bool:
    """Permission held in at least one scope (for list pages that filter by scope)."""
    return perm in effective(user, event, request=request).permissions


def require(request, event, perm: str, *, obj=None) -> None:
    if not has_perm(request.user, event, perm, obj=obj, request=request):
        raise PermissionDenied(perm)


def is_member(user, event, request=None) -> bool:
    return effective(user, event, request=request).member
