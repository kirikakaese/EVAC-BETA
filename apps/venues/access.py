# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who may see or edit a venue. Venues are shared between events, so access is derived from the events
that use the venue: a user may act on a venue when one of those events grants the permission with a
scope covering it (or event-wide). Instance admins may act on every venue."""
from __future__ import annotations

from apps.events import rbac
from apps.events.models import Event

from .models import Venue


def _venue_of(obj) -> Venue:
    if isinstance(obj, Venue):
        return obj
    if hasattr(obj, "venue"):
        return obj.venue
    return obj.building.venue  # Floor


def allowed(user, obj, perm: str, request=None) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    venue = _venue_of(obj)
    for event in Event.objects.filter(venues=venue, memberships__user=user).distinct():
        if rbac.has_perm(user, event, perm, obj=obj, request=request):
            return True
    return False


def visible(user, request=None):
    if user.is_superuser:
        return Venue.objects.all()
    ids = set()
    for event in Event.objects.visible_to(user).prefetch_related("venues"):
        access = rbac.effective(user, event, request=request).access
        scopes = access.scopes_for("venues.view")
        for v in event.venues.all():
            if scopes is None or ("venue", str(v.pk)) in scopes:
                ids.add(v.pk)
    return Venue.objects.filter(pk__in=ids)
