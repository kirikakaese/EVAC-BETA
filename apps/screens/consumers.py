# SPDX-License-Identifier: AGPL-3.0-or-later
"""WebSocket of a screen (``/ws/screen/``): device-token auth in the first message, heartbeats, commands.

Browsers cannot set headers on WebSockets and tokens in URLs end up in logs, so the player sends
``{"type": "auth", "token": "evacscreen_…", "since": <seq>}`` first; the server closes with 4401 if that
does not arrive within a few seconds or the token is invalid/revoked.
"""
from __future__ import annotations

import asyncio

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from . import channel, services

AUTH_TIMEOUT = 5


@database_sync_to_async
def _authenticate(token):
    return services.authenticate(token)


@database_sync_to_async
def _heartbeat(screen, data, ip):
    return services.heartbeat(screen, data, ip=ip)


@database_sync_to_async
def _still_valid(screen_id):
    from .models import Screen

    return Screen.objects.paired().filter(pk=screen_id).exists()


class ScreenConsumer(AsyncJsonWebsocketConsumer):
    screen = None

    async def connect(self):
        await self.accept()
        self._auth_timer = asyncio.get_running_loop().call_later(AUTH_TIMEOUT, self._auth_timeout)

    def _auth_timeout(self):
        if self.screen is None:
            asyncio.ensure_future(self.close(code=4401))

    async def disconnect(self, code):
        if getattr(self, "_auth_timer", None):
            self._auth_timer.cancel()
        if self.screen is not None:
            await self.channel_layer.group_discard(channel.group_name(self.screen.pk), self.channel_name)

    def _ip(self):
        client = self.scope.get("client") or (None, None)
        return client[0]

    async def receive_json(self, content, **kwargs):
        kind = content.get("type")
        if self.screen is None:
            if kind != "auth":
                await self.close(code=4401)
                return
            screen = await _authenticate(content.get("token"))
            if screen is None:
                await self.close(code=4401)
                return
            self.screen = screen
            self._auth_timer.cancel()
            await self.channel_layer.group_add(channel.group_name(screen.pk), self.channel_name)
            await self.send_json({"type": "hello", "screen": str(screen.pk), "seq": channel.last_seq(screen.pk)})
            for msg in channel.since(screen.pk, int(content.get("since") or 0)):
                await self.send_json(msg)
            return
        if kind == "heartbeat":
            if not await _still_valid(self.screen.pk):
                await self.close(code=4401)
                return
            reply = await _heartbeat(self.screen, content.get("data") or {}, self._ip())
            await self.send_json({"type": "heartbeat.ack", **reply})
        elif kind == "ping":
            await self.send_json({"type": "pong"})

    async def screen_message(self, event):
        msg = event["message"]
        await self.send_json(msg)
        if msg.get("type") == "revoked":
            await self.close(code=4401)
