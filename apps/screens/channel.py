# SPDX-License-Identifier: AGPL-3.0-or-later
"""Messages from the server to one screen (config changed, commands, revocation).

Like :mod:`apps.core.realtime`, but addressed to a single screen: a channel-layer group per screen for the
WebSocket and a short per-screen ring buffer in the cache for the SSE fallback. Best effort: a screen that
was offline picks up its state from ``/player/api/config/`` when it reconnects.
"""
from __future__ import annotations

import logging
import math
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


SPREAD_FROM = 50  # screens
SPREAD_PER_SECOND = 20  # refetches the server should see per second (leaves room for an alarm)
SPREAD_MAX = 60
SPREAD_TYPES = {"program.changed"}  # the player spreads these refetches; never evacuation messages


FAN_OUT = 32  # concurrent channel-layer sends of one send_many


BULK_LUA = """
local over = 0
local n = #KEYS
local now = ARGV[2 * n + 1]
local expiry = ARGV[2 * n + 2]
for i = 1, n do
    if redis.call('ZCOUNT', KEYS[i], '-inf', '+inf') < tonumber(ARGV[n + i]) then
        redis.call('ZADD', KEYS[i], now, ARGV[i])
        redis.call('EXPIRE', KEYS[i], expiry)
    else
        over = over + 1
    end
end
return over
"""


async def bulk_group_send(layer: Any, batch: list[tuple[str, dict[str, Any]]]) -> int:
    """``group_send`` for many groups at once on channels_redis with one Redis server: the group members of every
    group in one pipelined round trip, every message in one Lua call (the same script channels_redis runs per
    group). An alarm to 1,000 screens is then three round trips instead of four per screen. Raises
    ``NotImplementedError`` for other layers. Returns the number of messages dropped for a full channel."""
    try:
        from channels_redis.core import RedisChannelLayer
    except ImportError:  # pragma: no cover - channels_redis is a dependency
        raise NotImplementedError from None
    if not isinstance(layer, RedisChannelLayer) or layer.ring_size != 1 or not batch:
        raise NotImplementedError
    conn = layer.connection(0)
    now = time.time()
    pipe = conn.pipeline(transaction=False)
    for group, _message in batch:
        key = layer._group_key(group)
        pipe.zremrangebyscore(key, min=0, max=int(now) - layer.group_expiry)
        pipe.zrange(key, 0, -1)
    members = (await pipe.execute())[1::2]
    keys: list[Any] = []
    payloads: list[Any] = []
    capacities: list[Any] = []
    for (_group, message), names in zip(batch, members, strict=True):
        if not names:
            continue
        _by_conn, key_message, key_capacity = layer._map_channel_keys_to_connection(
            [n.decode("utf8") for n in names], message)
        for key, payload in key_message.items():
            keys.append(key)
            payloads.append(payload)
            capacities.append(key_capacity[key])
    if not keys:
        return 0
    pipe = conn.pipeline(transaction=False)
    for key in set(keys):
        pipe.zremrangebyscore(key, min=0, max=int(now) - int(layer.expiry))
    await pipe.execute()
    over = int(await conn.eval(BULK_LUA, len(keys), *keys, *payloads, *capacities, now, layer.expiry))
    if over:
        log.warning("channel layer: %d of %d messages dropped (channel full)", over, len(keys))
    return over


def _next_seqs(screen_ids: list[Any]) -> list[int]:
    """The next sequence number of every screen: one pipelined round trip on Redis (counters never expire), one
    add + incr per screen on other caches."""
    from django.core.cache import caches
    from django.core.cache.backends.redis import RedisCache

    keys = [_seq_key(sid) for sid in screen_ids]
    backend = caches["default"]
    if isinstance(backend, RedisCache):
        pipe = backend._cache.get_client(write=True).pipeline(transaction=False)
        for key in keys:
            pipe.incr(backend.make_and_validate_key(key))
        return [int(v) for v in pipe.execute()]
    out = []
    for key in keys:
        cache.add(key, 0, None)
        out.append(int(cache.incr(key)))
    return out


def send_many(items: list[tuple[Any, str, dict[str, Any]]]) -> int:
    """``send`` for many screens at once: ``[(screen id, type, data), ...]``. One pass over the cache and one
    hop into the channel layer instead of one per screen (an alarm reaches every screen of the event)."""
    msgs = []
    if len(items) > SPREAD_FROM:
        # many screens are told to refetch at once: ask them to spread the requests (players wait a random part)
        spread = min(SPREAD_MAX, math.ceil(len(items) / SPREAD_PER_SECOND))
        items = [(sid, t, {**d, "spread": spread} if t in SPREAD_TYPES else d) for sid, t, d in items]
    try:
        seqs = _next_seqs([sid for sid, _t, _d in items])
        now = time.time()
        for (sid, type_, data), seq in zip(items, seqs, strict=True):
            msgs.append((sid, {"seq": seq, "type": type_, "data": data, "ts": now}))
        bufs = cache.get_many([_buf_key(sid) for sid, _m in msgs])
        for sid, m in msgs:
            bufs[_buf_key(sid)] = [*(bufs.get(_buf_key(sid)) or []), m][-BUFFER_SIZE:]
        cache.set_many(bufs, BUFFER_TTL)
    except Exception as exc:  # noqa: BLE001
        log.warning("screen buffer unavailable: %s", exc)
        return 0
    try:
        import asyncio

        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is not None:
            async def fan_out() -> None:
                batch = [(group_name(sid), {"type": "screen.message", "message": m}) for sid, m in msgs]
                try:
                    await bulk_group_send(layer, batch)
                    return
                except NotImplementedError:
                    pass  # another channel layer (in-memory in tests and dev): one group_send per screen
                # a bounded number of concurrent sends: async_to_sync runs this on a fresh event loop with a fresh
                # Redis pool, and one connection per screen (1,000 handshakes) made an alarm take seconds
                gate = asyncio.Semaphore(FAN_OUT)

                async def one(sid: Any, m: dict[str, Any]) -> None:
                    async with gate:
                        await layer.group_send(group_name(sid), {"type": "screen.message", "message": m})

                results = await asyncio.gather(*(one(sid, m) for sid, m in msgs), return_exceptions=True)
                failed = [r for r in results if isinstance(r, BaseException)]
                if failed:  # one screen's failure must not stop the others
                    log.warning("channel layer: %d of %d sends failed: %s", len(failed), len(msgs), failed[0])

            async_to_sync(fan_out)()
    except Exception as exc:  # noqa: BLE001
        log.warning("channel layer unavailable: %s", exc)
    return len(msgs)
