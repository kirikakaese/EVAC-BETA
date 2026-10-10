# SPDX-License-Identifier: AGPL-3.0-or-later
"""The player page (``/player/``) and its service worker (``/player/sw.js``, scope ``/player/``)."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_safe

from apps.core.middleware import allow_code_frames

PLAYER_DIR = Path(settings.BASE_DIR) / "static" / "player"
BUNDLE = ("player.js", "player.css", "sw.js")


@lru_cache(maxsize=1)
def bundle_version() -> str:
    h = hashlib.sha256()
    for name in BUNDLE:
        p = PLAYER_DIR / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


def player_strings() -> dict[str, str]:
    return {
        "pair_title": _("Pair this screen"),
        "pair_step1": _("In EVAC open Screens → Pair a screen, or scan the QR code."),
        "pair_step2": _("Enter the code shown here."),
        "pair_waiting": _("Waiting for pairing…"),
        "no_server": _("EVAC server not reachable"),
        "retrying": _("Retrying automatically."),
        "Follow the instructions of the staff": _("Follow the instructions of the staff"),
        "Self-test": _("Self-test"), "This is a test. There is no alarm.": _("This is a test. There is no alarm."),
        "TEST": _("TEST"),
    }


@require_safe
def index(request):
    from evac import __version__

    env = {
        "version": f"{__version__}+{bundle_version()}",
        "api": "/player/api/",
        "ws": getattr(settings, "EVAC_REALTIME_URL", ""),
        "strings": player_strings(),
    }
    resp = render(request, "screens/player.html", {"env": env, "bundle_version": bundle_version()})
    resp["Cache-Control"] = "no-cache"
    return allow_code_frames(resp)


@require_safe
def service_worker(request):
    path = PLAYER_DIR / "sw.js"
    if not path.exists():
        raise Http404
    resp = HttpResponse(path.read_bytes(), content_type="text/javascript; charset=utf-8")
    resp["Service-Worker-Allowed"] = "/player/"
    resp["Cache-Control"] = "no-cache"
    return resp
