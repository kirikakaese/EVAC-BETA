# SPDX-License-Identifier: AGPL-3.0-or-later
"""WebSocket consumer for the per-event live stream (``/ws/e/<slug>/``)."""
from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from . import group_name, since


@database_sync_to_async
def _resolve(user, slug):
    from apps.events import rbac
    from apps.events.models import Event

    event = Event.objects.filter(slug=slug).first()
    if event is None or not getattr(user, "is_authenticated", False):
        return None
    return event if rbac.has_perm(user, event, "events.view") else None


class EventStreamConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        slug = self.scope["url_route"]["kwargs"]["slug"]
        event = await _resolve(self.scope.get("user"), slug)
        if event is None:
            await self.close(code=4403)
            return
        self.event_id = event.pk
        self.group = group_name(event.pk)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, "group", None):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # {"type": "resume", "since": <seq>} replays buffered messages; {"type": "ping"} -> pong
        if content.get("type") == "resume":
            for msg in since(self.event_id, int(content.get("since") or 0)):
                await self.send_json(msg)
        elif content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def evac_message(self, event):
        await self.send_json(event["message"])
