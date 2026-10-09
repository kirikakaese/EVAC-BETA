# SPDX-License-Identifier: AGPL-3.0-or-later
"""Device API of the playlists module (``/player/api/playlists/…``, screen token)."""
from django.http import JsonResponse
from django.urls import re_path
from django.views.decorators.http import require_safe

from apps.screens.player_api import _screen, _unauthorized

from . import services


@require_safe
def program(request):
    """Entries (overrides, schedules, default) with time windows and the playlists they use, for 7 days."""
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    return JsonResponse({"program": services.screen_program(screen)})


app_name = "playlists_player"
urlpatterns = [re_path(r"^program/$", program, name="program")]
