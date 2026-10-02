# SPDX-License-Identifier: AGPL-3.0-or-later
"""Realtime fan-out to browsers: WebSocket (Channels) with SSE and long-poll fallbacks.

``publish(event, type, data)`` sends a message to the channel-layer group of the event (WebSocket
clients) and appends it to a short ring buffer in the cache, from which the SSE stream and the long-poll
endpoint read. Messages carry a per-event sequence number so clients can resume after a reconnect.
Publishing never raises: realtime is best effort; durable state lives in the database.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache import cache

log = logging.getLogger("evac.realtime")

BUFFER_SIZE = 200
BUFFER_TTL = 3600


def group_name(event_id) -> str:
    return f"event.{event_id}"


def _seq_key(event_id) -> str:
    return f"rt:{event_id}:seq"


def _buf_key(event_id) -> str:
    return f"rt:{event_id}:buf"


def next_seq(event_id) -> int:
    key = _seq_key(event_id)
    cache.add(key, 0, None)
    try:
        return int(cache.incr(key))
    except ValueError:  # evicted between add and incr
        cache.set(key, 1, None)
        return 1


def publish(event, type_: str, data: dict[str, Any]) -> dict[str, Any] | None:
    try:
        msg = {"seq": next_seq(event.pk), "type": type_, "data": data, "ts": time.time()}
        buf = cache.get(_buf_key(event.pk)) or []
        buf.append(msg)
        cache.set(_buf_key(event.pk), buf[-BUFFER_SIZE:], BUFFER_TTL)
    except Exception as exc:  # noqa: BLE001
        log.warning("realtime buffer unavailable: %s", exc)
        return None
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(group_name(event.pk), {"type": "evac.message", "message": msg})
    except Exception as exc:  # noqa: BLE001
        log.warning("channel layer unavailable: %s", exc)
    return msg


def since(event_id, seq: int) -> list[dict[str, Any]]:
    return [m for m in (cache.get(_buf_key(event_id)) or []) if m["seq"] > seq]
