# SPDX-License-Identifier: AGPL-3.0-or-later
"""Device API of the content module for players (``/player/api/content/…``, screen token)."""
from django.http import Http404, JsonResponse
from django.urls import re_path
from django.views.decorators.http import require_safe

from apps.core import modules
from apps.screens.player_api import _screen, _unauthorized

from . import files, services


@require_safe
def theme(request):
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    if not modules.is_enabled("content", screen.event):
        return JsonResponse({"theme": None})
    payload = services.theme_payload(
        screen.event, lambda a: files.player_url(a.sha256, a.variants[a.variant("webp", "original")]["file"], screen),
        lambda ff: files.player_url(ff.sha256, "font.woff2", screen))
    return JsonResponse({"theme": payload})


@require_safe
def bundle(request):
    """Theme, fonts, published layouts and asset URLs of the screen's event (cached offline by the player)."""
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    if not modules.is_enabled("content", screen.event):
        return JsonResponse({"bundle": None})
    return JsonResponse({"bundle": services.bundle(
        screen.event, url_for=lambda sha, name: files.player_url(sha, name, screen),
        font_url_for=lambda ff: files.player_url(ff.sha256, "font.woff2", screen))})


@require_safe
def file(request, sha, name):
    screen = _screen(request) or files.screen_from_signature(request.GET.get("s", ""), sha)
    if screen is None:
        return _unauthorized()
    if not files.screen_may_read(screen, sha):
        raise Http404
    return files.respond(sha, name)


app_name = "content_player"
urlpatterns = [
    re_path(r"^theme/$", theme, name="theme"),
    re_path(r"^bundle/$", bundle, name="bundle"),
    re_path(r"^files/(?P<sha>[0-9a-f]{64})/(?P<name>[a-z0-9][a-z0-9_.-]{0,60})$", file, name="file"),
]
