# SPDX-License-Identifier: AGPL-3.0-or-later
"""SSE stream and long-poll fallback for clients without WebSockets."""
from __future__ import annotations

import asyncio
import json
import time

from asgiref.sync import sync_to_async
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, JsonResponse, StreamingHttpResponse

from . import since

SSE_MAX_SECONDS = 55
POLL_MAX_SECONDS = 10


def _event_for(request, slug):
    from apps.events import rbac
    from apps.events.models import Event

    event = Event.objects.filter(slug=slug).first()
    if event is None:
        raise Http404
    if not request.user.is_authenticated or not rbac.has_perm(request.user, event, "events.view"):
        raise PermissionDenied
    return event


@transaction.non_atomic_requests
async def sse(request, slug):
    event = await sync_to_async(_event_for)(request, slug)
    try:
        last = int(request.headers.get("Last-Event-ID") or request.GET.get("since") or 0)
    except ValueError:
        last = 0
    max_seconds = min(float(request.GET.get("max") or SSE_MAX_SECONDS), SSE_MAX_SECONDS)

    async def stream():
        nonlocal last
        deadline = time.monotonic() + max_seconds
        yield "retry: 2000\n\n"
        while time.monotonic() < deadline:
            for msg in await sync_to_async(since)(event.pk, last):
                last = msg["seq"]
                yield f"id: {msg['seq']}\ndata: {json.dumps(msg)}\n\n"
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    resp = StreamingHttpResponse(stream(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


def poll(request, slug):
    event = _event_for(request, slug)
    try:
        last = int(request.GET.get("since") or 0)
    except ValueError:
        last = 0
    wait = min(float(request.GET.get("wait") or POLL_MAX_SECONDS), POLL_MAX_SECONDS)
    deadline = time.monotonic() + wait
    while True:
        msgs = since(event.pk, last)
        if msgs or time.monotonic() >= deadline:
            return JsonResponse({"messages": msgs})
        time.sleep(0.5)
