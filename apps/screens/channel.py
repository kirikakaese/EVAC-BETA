# SPDX-License-Identifier: AGPL-3.0-or-later
"""Messages from the server to one screen (config changed, commands, revocation).

Like :mod:`apps.core.realtime`, but addressed to a single screen: a channel-layer group per screen for the
WebSocket and a short per-screen ring buffer in the cache for the SSE fallback. Best effort: a screen that
was offline picks up its state from ``/player/api/config/`` when it reconnects.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache import cache

log = logging.getLogger("evac.screens")

BUFFER_SIZE = 50
BUFFER_TTL = 3600


def group_name(screen_id) -> str:
    return f"screen.{screen_id}"


def _buf_key(screen_id) -> str:
    return f"scr:{screen_id}:buf"


def _seq_key(screen_id) -> str:
    return f"scr:{screen_id}:seq"


def send(screen, type_: str, data: dict[str, Any]) -> dict[str, Any] | None:
    try:
        cache.add(_seq_key(screen.pk), 0, None)
        msg = {"seq": int(cache.incr(_seq_key(screen.pk))), "type": type_, "data": data, "ts": time.time()}
        buf = cache.get(_buf_key(screen.pk)) or []
        buf.append(msg)
        cache.set(_buf_key(screen.pk), buf[-BUFFER_SIZE:], BUFFER_TTL)
    except Exception as exc:  # noqa: BLE001
        log.warning("screen buffer unavailable: %s", exc)
        return None
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(group_name(screen.pk), {"type": "screen.message", "message": msg})
    except Exception as exc:  # noqa: BLE001
        log.warning("channel layer unavailable: %s", exc)
    return msg


def since(screen_id, seq: int) -> list[dict[str, Any]]:
    return [m for m in (cache.get(_buf_key(screen_id)) or []) if m["seq"] > seq]


def last_seq(screen_id) -> int:
    return int(cache.get(_seq_key(screen_id)) or 0)
