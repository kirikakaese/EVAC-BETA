# SPDX-License-Identifier: AGPL-3.0-or-later
"""DRF permission classes.

* :class:`HasScope` (default): service tokens need ``<scope_module>:read`` for safe methods and
  ``<scope_module>:write`` otherwise. Views declare ``scope_module``; views without it accept any token.
* :class:`EventPermission`: ``event_permissions = {"GET": "events.view", "default": "events.manage"}`` checked
  against ``view.get_event()`` with the RBAC engine (scopes, two-factor rules).
"""
from rest_framework import permissions

from apps.events import rbac


class HasScope(permissions.BasePermission):
    message = "This token lacks the required scope."

    def has_permission(self, request, view):
        tok = getattr(request, "service_token", None)
        module = getattr(view, "scope_module", None)
        if tok is None or not module:
            return True
        mode = "read" if request.method in permissions.SAFE_METHODS else "write"
        return tok.has_scope(f"{module}:{mode}")


class EventPermission(permissions.BasePermission):
    message = "You do not have this permission in the event."

    def has_permission(self, request, view):
        perms = getattr(view, "event_permissions", {})
        perm = perms.get(request.method, perms.get("default"))
        if not perm:
            return True
        event = view.get_event()
        return rbac.has_perm(request.user, event, perm, request=request)


class IsSuperuser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)
