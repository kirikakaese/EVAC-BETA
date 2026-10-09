# SPDX-License-Identifier: AGPL-3.0-or-later
"""Serving stored files (assets, fonts) to portal users and to screens.

Files are only handed out to someone who may see them: a logged-in member with ``content.view`` in an event
that owns the file (shared library files: any member of any event), or a paired screen of such an event.
Content-addressed names never change, so responses are cacheable forever. SVGs get a sandboxing CSP.
"""
from __future__ import annotations

from django.http import FileResponse, Http404
from django.urls import reverse

from apps.events import rbac
from apps.events.models import Event

from . import services, storage

SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"


def portal_url(sha: str, name: str) -> str:
    return reverse("content_files:file", args=[sha, name])


def player_url(sha: str, name: str) -> str:
    return reverse("content_player:file", args=[sha, name])


def asset_url(asset, variant: str = "original", *, player: bool = False) -> str:
    name = asset.variants.get(variant, asset.variants["original"])["file"]
    return (player_url if player else portal_url)(asset.sha256, name)


def respond(sha: str, name: str):
    try:
        info = services.file_info(sha, name)
    except ValueError:
        raise Http404 from None
    if info is None or not info[0].exists():
        raise Http404
    path, mime = info
    resp = FileResponse(path.open("rb"), content_type=mime)
    resp["Cache-Control"] = "private, max-age=31536000, immutable"
    resp["X-Content-Type-Options"] = "nosniff"
    if mime == "image/svg+xml":
        resp["Content-Security-Policy"] = SVG_CSP
    return resp


def user_may_read(user, sha: str, request=None) -> bool:
    if not user.is_authenticated:
        return False
    if not storage.SHA.match(sha):
        return False
    events, shared = services.file_owner_events(sha)
    if user.is_superuser:
        return bool(events) or shared
    if shared and Event.objects.visible_to(user).exists():
        return True
    return any(rbac.has_perm(user, e, "content.view", request=request) for e in Event.objects.filter(pk__in=events))


def screen_may_read(screen, sha: str) -> bool:
    if not storage.SHA.match(sha):
        return False
    events, shared = services.file_owner_events(sha)
    return shared or screen.event_id in events
