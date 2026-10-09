# SPDX-License-Identifier: AGPL-3.0-or-later
"""Device API of custom widgets: ``/player/api/widgets/data/`` (screen token) - every widget of the event with its
current rows. The player keeps the last answer for offline use and asks again on ``data.changed``."""
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_safe

from apps.core import modules
from apps.screens.player_api import _screen, _unauthorized

from . import services


@require_safe
def data(request):
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    if not modules.is_enabled("widgets", screen.event):
        return JsonResponse({"widgets": {}})
    return JsonResponse({"widgets": services.event_payload(screen.event)})


app_name = "widgets_player"
urlpatterns = [path("data/", data, name="data")]
