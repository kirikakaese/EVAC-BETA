# SPDX-License-Identifier: AGPL-3.0-or-later
"""Device API of announcements for players: the spoken files (``/player/api/announcements/speech/<file>``)."""
from django.http import FileResponse, Http404
from django.urls import re_path
from django.views.decorators.http import require_safe

from apps.screens.player_api import _screen, _unauthorized

from . import services, tts
from .models import Announcement


@require_safe
def speech(request, name):
    screen = _screen(request) or services.screen_for_speech(request.GET.get("s", ""), name)
    if screen is None:
        return _unauthorized()
    if not Announcement.objects.filter(event=screen.event, speech_file=name).exists():
        raise Http404
    path = tts.path_of(name)
    if not path.is_file():
        raise Http404
    resp = FileResponse(path.open("rb"), content_type="audio/mp4" if name.endswith(".m4a") else "audio/wav")
    resp["Cache-Control"] = "private, max-age=31536000, immutable"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


app_name = "announcements_player"
urlpatterns = [re_path(rf"^speech/(?P<name>{tts.KEY})$", speech, name="speech")]
