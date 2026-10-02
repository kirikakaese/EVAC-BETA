# SPDX-License-Identifier: AGPL-3.0-or-later
"""Middleware, health/metrics, notifications, realtime fallbacks."""
import json

import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import override_settings

from apps.core import realtime
from apps.core.models import Notification
from apps.core.notify import notify, unread_count
from apps.core.webhooks import emit


@pytest.mark.django_db
def test_first_run_redirects_to_setup(client):
    r = client.get("/")
    assert r.status_code == 302 and r["Location"] == "/setup/"
    assert client.get("/api/v1/health/").status_code == 503
    assert client.get("/healthz").status_code == 200


@pytest.mark.django_db
def test_csp_header_and_nonce(admin_client, event):
    r = admin_client.get("/e/demo/")
    csp = r["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
    nonce = csp.split("'nonce-")[1].split("'")[0]
    assert f'nonce="{nonce}"' in r.content.decode()
    assert "frame-ancestors 'none'" in csp


@pytest.mark.django_db
@override_settings(EVAC_RATE_LIMITS={"login": 2})
def test_rate_limit(client, admin):
    for _ in range(2):
        client.post("/accounts/login/", {"email": "x@example.org", "password": "y"})
    assert client.post("/accounts/login/", {"email": "x@example.org", "password": "y"}).status_code == 429


@pytest.mark.django_db
def test_health_ready_metrics(client, admin, event):
    assert client.get("/readyz").json()["status"] == "ok"
    body = client.get("/metrics").content.decode()
    assert "evac_outbox_depth 0" in body and 'evac_events{state="draft"} 1' in body
    with override_settings(EVAC_METRICS_TOKEN="t0k"):
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", HTTP_AUTHORIZATION="Bearer t0k").status_code == 200


@pytest.mark.django_db
def test_notifications(client, user, event):
    notify([user], "Screen offline", body="Hall A", url="/e/demo/", level="warn", event=event)
    notify([user], "Plain")
    assert unread_count(user) == 2
    client.force_login(user)
    assert "Screen offline" in client.get("/notifications/").content.decode()
    n = Notification.objects.get(title="Screen offline")
    r = client.post(f"/notifications/{n.pk}/read/")
    assert r["Location"] == "/e/demo/"
    client.post("/notifications/read-all/")
    assert unread_count(user) == 0


@pytest.mark.django_db
def test_realtime_buffer_and_poll(client, member, event):
    emit("event.updated", {"slug": "demo"}, event=event)
    msgs = realtime.since(event.pk, 0)
    assert msgs[-1]["type"] == "event.updated"
    client.force_login(member)
    r = client.get("/poll/e/demo/?since=0&wait=0")
    assert r.json()["messages"][-1]["data"] == {"slug": "demo"}
    last = msgs[-1]["seq"]
    assert client.get(f"/poll/e/demo/?since={last}&wait=0").json()["messages"] == []
    with pytest.raises(KeyError):
        emit("not.registered", {}, event=event)


@pytest.mark.django_db(transaction=True)
def test_sse_stream(member, event):
    from django.test import AsyncClient

    emit("event.updated", {"slug": "demo"}, event=event)

    async def run():
        client = AsyncClient()
        await client.aforce_login(member)
        resp = await client.get("/sse/e/demo/?since=0&max=0.5")
        assert resp.status_code == 200 and resp["Content-Type"] == "text/event-stream"
        chunks = [c async for c in resp.streaming_content]
        return b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks).decode()

    body = async_to_sync(run)()
    assert body.startswith("retry: 2000") and '"type": "event.updated"' in body and "id: " in body


@pytest.mark.django_db
def test_realtime_requires_membership(client, other, event):
    client.force_login(other)
    assert client.get("/poll/e/demo/?wait=0").status_code in (403, 404)


@pytest.mark.django_db
def test_seq_survives_eviction(event):
    cache.delete(realtime._seq_key(event.pk))
    assert realtime.next_seq(event.pk) == 1


@pytest.mark.django_db(transaction=True)
def test_websocket_stream(member, event):
    from evac.asgi import application

    async def run():
        from channels.db import database_sync_to_async

        comm = WebsocketCommunicator(application, "/ws/e/demo/", headers=[(b"origin", b"http://testserver"),
                                                                          (b"host", b"testserver")])
        comm.scope["user"] = member
        connected, _ = await comm.connect()
        assert connected
        await database_sync_to_async(realtime.publish)(event, "event.updated", {"x": 1})
        msg = await comm.receive_json_from(timeout=2)
        assert msg["type"] == "event.updated"
        await comm.send_json_to({"type": "ping"})
        assert (await comm.receive_json_from())["type"] == "pong"
        await comm.send_json_to({"type": "resume", "since": msg["seq"] - 1})
        assert (await comm.receive_json_from())["data"] == {"x": 1}
        await comm.disconnect()

    async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
def test_websocket_rejects_strangers(other, event):
    from evac.asgi import application

    async def run():
        comm = WebsocketCommunicator(application, "/ws/e/demo/", headers=[(b"origin", b"http://testserver"),
                                                                          (b"host", b"testserver")])
        comm.scope["user"] = other
        connected, _ = await comm.connect()
        assert not connected

    async_to_sync(run)()


def test_json_formatter():
    import logging

    from apps.core.logging import JsonFormatter

    rec = logging.makeLogRecord({"msg": "hello %s", "args": ("x",), "levelname": "INFO", "name": "evac", "screen": 3})
    data = json.loads(JsonFormatter().format(rec))
    assert data["msg"] == "hello x" and data["screen"] == 3
