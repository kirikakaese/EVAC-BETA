# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers shared by portal views of every app."""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from apps.events import rbac
from apps.events.models import Event


def get_event(request, slug: str) -> Event:
    event = get_object_or_404(Event.objects.visible_to(request.user), slug=slug)
    request.event = event
    if hasattr(request, "session") and request.session.get("current_event") != slug:
        request.session["current_event"] = slug
    return event


def can_acknowledge(request, event, key: str) -> bool:
    return any(rbac.has_any(request.user, event, p, request=request) for p in ("modules.manage", f"{key}.manage"))


def acknowledgement_gate(request, event, key: str):
    """The module's statement, to be accepted once for this event before any of its pages work."""
    from django.shortcuts import render

    from apps.core.registry import registry

    spec = registry.ensure_loaded().modules[key]
    return render(request, "portal/acknowledge.html", {
        "event": event, "spec": spec, "can": can_acknowledge(request, event, key),
        "next": request.get_full_path() if request.method == "GET" else ""}, status=403 if request.method != "GET"
        else 200)


def event_view(perm: str | None = "events.view", module: str | None = None):
    """Decorator for ``view(request, slug, ..., event=...)``: login, membership, permission, module checks."""

    def deco(fn):
        @wraps(fn)
        def wrapper(request, slug, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            event = get_event(request, slug)
            if module is not None:
                from django.http import Http404

                from apps.core import modules

                if not modules.is_enabled(module, event):
                    raise Http404("Module disabled")
            if perm and not rbac.has_any(request.user, event, perm, request=request):
                raise PermissionDenied(perm)
            if module is not None and modules.acknowledgement_needed(module, event):
                return acknowledgement_gate(request, event, module)
            return fn(request, slug, *args, event=event, **kwargs)

        return wrapper

    return deco


def superuser_view(fn):
    @wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_superuser:
            raise PermissionDenied
        return fn(request, *args, **kwargs)

    return wrapper
