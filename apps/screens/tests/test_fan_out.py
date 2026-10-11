# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fan-out to many screens on the Redis channel layer (ADR-0047): every message arrives, none is dropped."""
import asyncio
import os

import pytest

from apps.screens import channel

REDIS = os.environ.get("REDIS_TEST_URL", "redis://127.0.0.1:6379/12")


def redis_layer(**config):
    redis = pytest.importorskip("redis")
    try:
        redis.Redis.from_url(REDIS, socket_connect_timeout=1).ping()
    except redis.RedisError:
        pytest.skip("no Redis at REDIS_TEST_URL")
    from channels_redis.core import RedisChannelLayer

    return RedisChannelLayer(hosts=[REDIS], **config)


def test_bulk_group_send_reaches_every_member_once():
    layer = redis_layer(capacity=5000)

    async def run():
        await layer.flush()
        chans = [await layer.new_channel() for _ in range(300)]  # one process: all share one Redis key
        for i, c in enumerate(chans):
            await layer.group_add(f"screen.{i}", c)
        await layer.group_add("screen.0", extra := await layer.new_channel())  # a screen with two connections
        dropped = await channel.bulk_group_send(
            layer, [(f"screen.{i}", {"type": "screen.message", "n": i}) for i in range(300)]
            + [("screen.nobody", {"type": "screen.message", "n": -1})])
        got = [await asyncio.wait_for(layer.receive(c), 2) for c in chans]
        second = await asyncio.wait_for(layer.receive(extra), 2)
        await layer.flush()
        return dropped, got, second

    dropped, got, second = asyncio.run(run())
    assert dropped == 0
    assert [m["n"] for m in got] == list(range(300)) and second["n"] == 0


def test_capacity_overflow_is_reported_not_silent():
    layer = redis_layer(capacity=10)

    async def run():
        await layer.flush()
        chans = [await layer.new_channel() for _ in range(30)]
        for i, c in enumerate(chans):
            await layer.group_add(f"screen.{i}", c)
        dropped = await channel.bulk_group_send(layer, [(f"screen.{i}", {"type": "screen.message"}) for i in range(30)])
        await layer.flush()
        return dropped

    assert asyncio.run(run()) == 20


def test_other_layers_fall_back():
    from channels.layers import InMemoryChannelLayer

    with pytest.raises(NotImplementedError):
        asyncio.run(channel.bulk_group_send(InMemoryChannelLayer(), [("g", {"type": "x"})]))
