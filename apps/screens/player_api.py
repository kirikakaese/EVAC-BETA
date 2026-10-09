# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP API of the screen player (``/player/api/…``), authenticated with the per-screen device token.

``Authorization: Screen evacscreen_…`` (``Bearer`` works too). No cookies, no CSRF: players are not
browsers of a logged-in user. Pairing endpoints are rate limited (see ``RATE_LIMITED_PATHS``).
"""
from __future__ import annotations

import asyncio
import json
import time

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.audit import client_ip

from . import channel, services
from .models import PairingRequest, Screen

SSE_MAX_SECONDS = 55
POLL_MAX_SECONDS = 10


def _json_body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _token(request) -> str:
    auth = request.headers.get("Authorization", "")
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() in ("screen", "bearer"):
        return parts[1]
    return ""


def _screen(request) -> Screen | None:
    return services.authenticate(_token(request))


def _unauthorized():
    return JsonResponse({"detail": "Invalid or revoked screen token. Pair the screen again."}, status=401)


def screen_payload(screen: Screen) -> dict:
    cfg = services.screen_settings(screen.event)
    return {
        "screen": {
            "id": str(screen.pk), "name": screen.name, "tags": screen.tags,
            "venue": screen.venue.name if screen.venue_id else None,
            "zone": screen.zone.name if screen.zone_id else None,
            "room": screen.room.name if screen.room_id else None,
            "groups": [{"id": str(g.pk), "name": g.name} for g in screen.groups()],
        },
        "event": {"slug": screen.event.slug, "name": screen.event.name, "timezone": screen.event.timezone},
        "settings": cfg,
        "server_time": time.time(),
        "seq": channel.last_seq(screen.pk),
    }


@csrf_exempt
@require_POST
def pair_start(request):
    """A new player asks for a pairing code."""
    req, secret = services.start_pairing(ip=client_ip(request), user_agent=request.headers.get("User-Agent", ""),
                                         info=_json_body(request).get("info") or {})
    path = reverse("screens_global:pair") + f"?code={req.code}"
    base = settings.EVAC_PUBLIC_URL or request.build_absolute_uri("/").rstrip("/")
    return JsonResponse({"id": str(req.pk), "code": req.display_code, "secret": secret,
                         "expires_in": PairingRequest.TTL_MINUTES * 60, "pair_url": base + path}, status=201)


@csrf_exempt
@require_POST
def pair_status(request, pk):
    """The waiting player polls here with its secret (header ``X-Pairing-Secret``)."""
    req = get_object_or_404(PairingRequest.objects.select_related("screen__event"), pk=pk)
    try:
        return JsonResponse(services.pairing_status(req, request.headers.get("X-Pairing-Secret", "")))
    except PermissionError:
        raise Http404 from None


@require_GET
def config(request):
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    return JsonResponse(screen_payload(screen))


@csrf_exempt
@require_POST
def heartbeat(request):
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    reply = services.heartbeat(screen, _json_body(request).get("data") or {}, ip=client_ip(request))
    return JsonResponse({"type": "heartbeat.ack", **reply})


@transaction.non_atomic_requests
async def stream(request):
    """Server-sent events for one screen (WebSocket fallback). The player reads it with ``fetch``."""
    screen = await sync_to_async(_screen)(request)
    if screen is None:
        return _unauthorized()
    try:
        last = int(request.headers.get("Last-Event-ID") or request.GET.get("since") or 0)
    except ValueError:
        last = 0

    async def events():
        nonlocal last
        deadline = time.monotonic() + SSE_MAX_SECONDS
        yield "retry: 2000\n\n"
        while time.monotonic() < deadline:
            for msg in await sync_to_async(channel.since)(screen.pk, last):
                last = msg["seq"]
                yield f"id: {msg['seq']}\ndata: {json.dumps(msg)}\n\n"
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    resp = StreamingHttpResponse(events(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


@require_GET
def poll(request):
    screen = _screen(request)
    if screen is None:
        return _unauthorized()
    try:
        last = int(request.GET.get("since") or 0)
    except ValueError:
        last = 0
    wait = min(float(request.GET.get("wait") or POLL_MAX_SECONDS), POLL_MAX_SECONDS)
    deadline = time.monotonic() + wait
    while True:
        msgs = channel.since(screen.pk, last)
        if msgs or time.monotonic() >= deadline:
            return JsonResponse({"messages": msgs})
        time.sleep(0.5)
