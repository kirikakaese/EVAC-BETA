# SPDX-License-Identifier: AGPL-3.0-or-later
"""Player endpoints of the evacuation module (``/player/api/evacuation/``), ADR-0033/0034.

- ``GET state/``: the screen's current payload plus its *evacuation bundle* (everything needed to show every
  stage offline: texts, layouts, sounds, the event's public keys, precomputed directions, fallback origins).
- ``POST ack/``: the screen rendered payload ``v`` (latency and "X of Y confirmed", roadmap 3.8).
- ``POST selftest/``: the result of a self-test the control room asked for (roadmap 3.9).
- ``GET speech/<name>``: a spoken message (signed per screen, so ``<audio>`` and the service worker can fetch it).
- ``GET /evac/state``: the event-wide signed state for fallback origins (no token; the signature is the trust).
"""
from __future__ import annotations

import json
from typing import Any

from django.core import signing
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core import modules

from . import alarmkey, feed


def _screen(request: HttpRequest) -> Any:
    from apps.screens.player_api import _screen as screen_of

    return screen_of(request)


def _unauthorized() -> JsonResponse:
    return JsonResponse({"error": "unauthorized"}, status=401)


@require_GET
def state(request: HttpRequest) -> JsonResponse:
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    if not modules.is_enabled("evacuation", screen.event):
        return JsonResponse({"enabled": False})
    body = feed.payloads(screen.event, [screen]).get(str(screen.pk))
    bundle = feed.bundle(screen)
    from . import acks

    acks.bundle_served(screen, bundle["version"])
    return JsonResponse({"enabled": True, "payload": feed.sign(screen.event, body) if body else None,
                         "bundle": bundle})


def _json(request: HttpRequest) -> dict[str, Any] | JsonResponse:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "body must be JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "body must be a JSON object"}, status=400)
    return data


@csrf_exempt
@require_POST
def selftest(request: HttpRequest) -> JsonResponse:
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    data = _json(request)
    if isinstance(data, JsonResponse):
        return data
    from . import acks

    acks.record_selftest(screen, data)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def ack(request: HttpRequest) -> JsonResponse:
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    data = _json(request)
    if isinstance(data, JsonResponse):
        return data
    from . import acks

    acks.record(screen, data)
    return JsonResponse({"ok": True})


@require_GET
def speech(request: HttpRequest, name: str) -> HttpResponse:
    sid, _sep, sig = request.GET.get("s", "").partition(".")
    if not sig or signing.Signer(salt="evac-speech").signature(f"{sid}:{name}") != sig:
        raise Http404
    from django.apps import apps

    if not apps.is_installed("apps.announcements"):
        raise Http404
    from apps.announcements import tts

    path = tts.path_of(name)
    if not path.exists():
        raise Http404
    resp = FileResponse(path.open("rb"), content_type="audio/mp4" if name.endswith(".m4a") else "audio/wav")
    resp["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@require_GET
def fallback_state(request: HttpRequest, slug: str) -> JsonResponse:
    """Signed event-wide state, also served by secondary nodes and bridges (ADR-0003). Read-only and signed."""
    from apps.events.models import Event

    event = Event.objects.filter(slug=slug).first()
    if event is None or not modules.is_enabled("evacuation", event):
        raise Http404
    resp = JsonResponse(alarmkey.state_message(event))
    resp["Cache-Control"] = "no-store"
    resp["Access-Control-Allow-Origin"] = "*"
    return resp
