# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt
import json

import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken
from apps.core import modules
from apps.core.a11y import audit_url
from apps.core.models import AuditLog, Notification
from apps.events import services as event_services
from apps.screens import channel, services
from apps.screens.models import PairingRequest, Screen, ScreenGroup
from apps.venues.models import Room, Zone
from conftest import login_2fa


def start(client):
    r = client.post("/player/api/pair/", data=json.dumps({"info": {"resolution": "1920x1080", "evil": "x"}}),
                    content_type="application/json")
    assert r.status_code == 201
    return r.json()


def status(client, data, secret=None):
    return client.post(f"/player/api/pair/{data['id']}/", HTTP_X_PAIRING_SECRET=secret or data["secret"])


def device(token):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Screen {token}")
    return c


@pytest.fixture
def paired(client, admin, event):
    data = start(client)
    screen = services.pair(event, data["code"], actor=admin, name="Foyer", tags=["Foyer", "portrait"])
    token = status(client, data).json()["token"]
    return screen, token


@pytest.mark.django_db
def test_pairing_flow(client, admin, event):
    data = start(client)
    assert len(data["code"]) == 7 and data["pair_url"].endswith(f"/screens/pair/?code={data['code'].replace('-', '')}")
    assert status(client, data).json()["status"] == "pending"
    assert status(client, data, "wrong").status_code == 404
    login_2fa(client, admin)
    r = client.get(f"/e/demo/screens/pair/?code={data['code']}")
    assert data["code"] in r.content.decode()
    zone = Zone.objects.get(name="North")
    r = client.post("/e/demo/screens/pair/", {"code": data["code"].lower(), "name": "Foyer left",
                                               "zone": str(zone.pk), "tags": "foyer, Portrait"})
    screen = Screen.objects.get(name="Foyer left")
    assert r.status_code == 302 and r["Location"] == f"/e/demo/screens/{screen.pk}/"
    assert screen.venue == zone.venue and screen.tags == ["foyer", "portrait"]
    assert screen.reported == {"resolution": "1920x1080"}
    reply = status(client, data).json()
    assert reply["status"] == "paired" and reply["token"].startswith("evacscreen_")
    assert reply["screen"]["name"] == "Foyer left"
    assert status(client, data).json() == {"status": "delivered"}  # the token is handed out once
    assert services.authenticate(reply["token"]) == screen
    assert AuditLog.objects.filter(action="screen.paired").exists()
    # the code cannot be used twice
    r = client.post("/e/demo/screens/pair/", {"code": data["code"]})
    assert "No screen is waiting" in r.content.decode()


@pytest.mark.django_db
def test_expired_code_and_bad_input(client, admin, event):
    data = start(client)
    PairingRequest.objects.update(expires_at=timezone.now() - dt.timedelta(seconds=1))
    assert status(client, data).json() == {"status": "expired"}
    login_2fa(client, admin)
    r = client.post("/e/demo/screens/pair/", {"code": data["code"]})
    assert "No screen is waiting" in r.content.decode()
    assert "six characters" in client.post("/e/demo/screens/pair/", {"code": "AB"}).content.decode()
    assert services.purge_pairing_requests() == 0
    PairingRequest.objects.update(expires_at=timezone.now() - dt.timedelta(days=2))
    assert services.purge_pairing_requests() == 1


@pytest.mark.django_db
def test_device_api_and_revoke(client, admin, event, paired):
    screen, token = paired
    assert device("evacscreen_nope").get("/player/api/config/").status_code == 401
    cfg = device(token).get("/player/api/config/").json()
    assert cfg["screen"]["name"] == "Foyer" and cfg["event"]["slug"] == "demo"
    assert cfg["settings"]["heartbeat_seconds"] == 10 and cfg["settings"]["offline_after_seconds"] == 60
    r = device(token).post("/player/api/heartbeat/", {"data": {"version": "1.0", "uptime": 12, "errors": ["e"] * 20,
                                                               "slide": "x" * 500}}, format="json")
    assert r.json()["type"] == "heartbeat.ack" and r.json()["server_time"] > 0
    screen.refresh_from_db()
    assert screen.reported["version"] == "1.0" and len(screen.reported["errors"]) == 10
    assert len(screen.reported["slide"]) == 200 and screen.last_seen_at is not None
    assert screen.health() == Screen.Health.ONLINE
    channel.send(screen, "identify", {"seconds": 5})
    msgs = device(token).get("/player/api/poll/?since=0&wait=0").json()["messages"]
    assert msgs[-1]["type"] == "identify"
    login_2fa(client, admin)
    client.post(f"/e/demo/screens/{screen.pk}/revoke/")
    screen.refresh_from_db()
    assert screen.revoked_at is not None and screen.health() == Screen.Health.REVOKED
    assert device(token).get("/player/api/config/").status_code == 401
    assert device(token).post("/player/api/heartbeat/", {}, format="json").status_code == 401
    assert device(token).get("/player/api/poll/").status_code == 401


@pytest.mark.django_db(transaction=True)
def test_sse_stream(client, admin, event, paired):
    screen, token = paired
    channel.send(screen, "reload", {})
    r = client.get("/player/api/stream/?since=0", HTTP_AUTHORIZATION=f"Screen {token}")
    assert r["Content-Type"] == "text/event-stream"

    async def first_chunks():
        out = ""
        async for chunk in r.streaming_content:
            out += chunk.decode() if isinstance(chunk, bytes) else chunk
            if "reload" in out:
                return out
        return out

    assert '"reload"' in async_to_sync(first_chunks)()
    assert client.get("/player/api/stream/", HTTP_AUTHORIZATION="Screen nope").status_code == 401


@pytest.mark.django_db
def test_repair_moves_screen_to_new_device(client, admin, event, paired):
    screen, old = paired
    data = start(client)
    login_2fa(client, admin)
    r = client.post("/e/demo/screens/pair/", {"code": data["code"], "screen": str(screen.pk)})
    assert r.status_code == 302
    new = status(client, data).json()["token"]
    assert services.authenticate(old) is None and services.authenticate(new) == screen
    assert Screen.objects.count() == 1 and AuditLog.objects.filter(action="screen.repaired").exists()


@pytest.mark.django_db
def test_health_sweep_alerts(client, admin, event, paired, orga):
    screen, token = paired
    device(token).post("/player/api/heartbeat/", {"data": {}}, format="json")
    assert services.sweep_health() == 0
    later = timezone.now() + dt.timedelta(seconds=40)
    assert services.sweep_health(now=later) == 1
    assert Screen.objects.get(pk=screen.pk).health_state == "stale"
    assert services.sweep_health(now=timezone.now() + dt.timedelta(seconds=120)) == 1
    assert Screen.objects.get(pk=screen.pk).health_state == "offline"
    note = Notification.objects.get(user=orga)
    assert "Foyer" in note.title and note.level == "warning"
    device(token).post("/player/api/heartbeat/", {"data": {}}, format="json")
    assert Screen.objects.get(pk=screen.pk).health_state == "online"


@pytest.mark.django_db
def test_groups_and_scoped_access(client, admin, event, paired, user, role):
    screen, _token = paired
    login_2fa(client, admin)
    north = Zone.objects.get(name="North")
    r = client.post("/e/demo/screens/groups/", {"new-name": "Foyer screens", "new-kind": "dynamic",
                                                "new-match_tags": "foyer", "new-match_zones": [str(north.pk)]})
    group = ScreenGroup.objects.get(name="Foyer screens")
    assert r.status_code == 302 and list(group.screens()) == [screen]
    other = Screen.objects.create(event=event, name="Stage", room=Room.objects.get(name="Hall A"))
    assert set(group.screens()) == {screen}
    other.zone = north
    other.save()
    assert set(group.screens()) == {screen, other}
    manual = ScreenGroup.objects.create(event=event, name="Bar")
    client.post(f"/e/demo/screens/{screen.pk}/", {"screen-name": "Foyer", "screen-tags": "", "screen-groups":
                                                  [str(manual.pk)]})
    screen.refresh_from_db()
    assert screen.tags == [] and {g.name for g in screen.groups()} == {"Bar"}
    assert client.post("/e/demo/screens/groups/", {"new-name": "bar", "new-kind": "manual"}).status_code == 200
    # a user who may only see the "Bar" group sees only its screen
    event_services.assign_role(event, user, role("viewer"), scope_kind="screen_group", scope_id=str(manual.pk))
    client.force_login(user)
    page = client.get("/e/demo/screens/").content.decode()
    assert "Foyer" in page and "Stage" not in page
    assert client.get(f"/e/demo/screens/{other.pk}/").status_code == 403
    assert client.get(f"/e/demo/screens/{screen.pk}/").status_code == 200
    assert client.post(f"/e/demo/screens/{screen.pk}/revoke/").status_code == 403
    login_2fa(client, admin)
    client.post(f"/e/demo/screens/groups/{manual.pk}/", {"delete": "1"})
    assert not ScreenGroup.objects.filter(name="Bar").exists()


@pytest.mark.django_db
def test_module_off(client, admin, event, paired):
    screen, token = paired
    modules.set_event(event, "screens", False)
    login_2fa(client, admin)
    assert client.get("/e/demo/screens/").status_code == 404
    _tok, raw = ServiceToken.issue(name="t", owner=admin, created_with_2fa=True)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert api.get("/api/v1/events/demo/screens/").status_code == 404
    assert "Screens" not in client.get("/e/demo/").content.decode().split("<main")[0]


@pytest.mark.django_db
def test_api(client, admin, event, paired):
    screen, _token = paired
    _tok, raw = ServiceToken.issue(name="t", owner=admin, scopes=["screens:read"], created_with_2fa=True)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    rows = api.get("/api/v1/events/demo/screens/").json()
    rows = rows["results"] if isinstance(rows, dict) else rows
    assert rows[0]["name"] == "Foyer" and rows[0]["health"] == "offline" and rows[0]["paired"] is True
    assert api.patch(f"/api/v1/events/demo/screens/{screen.pk}/", {"name": "X"}, format="json").status_code == 403
    _tok, raw = ServiceToken.issue(name="w", owner=admin, scopes=["screens:read", "screens:write"],
                                   created_with_2fa=True)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    room = Room.objects.get(name="Hall A")
    r = api.patch(f"/api/v1/events/demo/screens/{screen.pk}/", {"name": "Lobby", "room": str(room.pk)},
                  format="json")
    assert r.status_code == 200 and r.json()["name"] == "Lobby"
    assert Screen.objects.get(pk=screen.pk).room == room
    g = api.post("/api/v1/events/demo/screen-groups/", {"name": "Halls", "kind": "dynamic",
                                                        "match_rooms": [str(room.pk)]}, format="json")
    assert g.status_code == 201 and g.json()["screens"] == [str(screen.pk)]
    assert api.post("/api/v1/events/demo/screen-groups/", {"name": "halls"}, format="json").status_code == 400
    data = start(client)
    r = api.post("/api/v1/events/demo/screens/pair/", {"code": data["code"], "name": "Bar"}, format="json")
    assert r.status_code == 201 and r.json()["name"] == "Bar"
    assert api.post("/api/v1/events/demo/screens/pair/", {"code": "ZZZZZZ"}, format="json").status_code == 400
    assert api.post(f"/api/v1/events/demo/screens/{screen.pk}/revoke/").json()["revoked_at"]
    assert api.delete(f"/api/v1/events/demo/screens/{screen.pk}/").status_code == 204
    assert api.delete(f"/api/v1/events/demo/screen-groups/{g.json()['id']}/").status_code == 204


@pytest.mark.django_db
def test_pair_global_picks_event(client, admin, event):
    assert client.get("/screens/pair/?code=ABC").status_code == 302  # login first
    login_2fa(client, admin)
    r = client.get("/screens/pair/?code=abc-def")
    assert r.status_code == 302 and r["Location"] == "/e/demo/screens/pair/?code=ABCDEF"
    event_services.create_event(name="Other", slug="other", user=admin, timezone="UTC",
                                start_date=dt.date(2026, 8, 1), end_date=dt.date(2026, 8, 2))
    page = client.get("/screens/pair/?code=ABCDEF").content.decode()
    assert "/e/other/screens/pair/?code=ABCDEF" in page and "/e/demo/screens/pair/?code=ABCDEF" in page


@pytest.mark.django_db
@override_settings(EVAC_EARLY_ACCESS_PASSWORD="secret")
def test_player_bypasses_early_access(client, admin, event):
    assert client.get("/e/demo/").status_code == 302
    assert client.post("/player/api/pair/", data="{}", content_type="application/json").status_code == 201


@pytest.mark.django_db(transaction=True)
def test_websocket(client, admin, event, paired):
    screen, token = paired
    from evac.asgi import application

    async def run():
        from channels.db import database_sync_to_async

        headers = [(b"origin", b"http://testserver"), (b"host", b"testserver")]
        comm = WebsocketCommunicator(application, "/ws/screen/", headers=headers)
        assert (await comm.connect())[0]
        await comm.send_json_to({"type": "auth", "token": "evacscreen_wrong"})
        assert (await comm.receive_output(timeout=2))["type"] == "websocket.close"

        comm = WebsocketCommunicator(application, "/ws/screen/", headers=headers)
        await comm.connect()
        await comm.send_json_to({"type": "auth", "token": token, "since": 0})
        hello = await comm.receive_json_from(timeout=2)
        assert hello["type"] == "hello" and hello["screen"] == str(screen.pk)
        await comm.send_json_to({"type": "heartbeat", "data": {"version": "ws"}})
        ack = await comm.receive_json_from(timeout=2)
        assert ack["type"] == "heartbeat.ack"
        await database_sync_to_async(channel.send)(screen, "identify", {})
        assert (await comm.receive_json_from(timeout=2))["type"] == "identify"
        await comm.send_json_to({"type": "ping"})
        assert (await comm.receive_json_from(timeout=2))["type"] == "pong"
        await database_sync_to_async(services.revoke)(screen, actor=admin)
        assert (await comm.receive_json_from(timeout=2))["type"] == "revoked"
        await comm.disconnect()

    async_to_sync(run)()
    assert Screen.objects.get(pk=screen.pk).reported["version"] == "ws"


@pytest.mark.django_db
def test_pages_accessible(client, admin, event, paired):
    screen, _token = paired
    group = ScreenGroup.objects.create(event=event, name="Bar")
    login_2fa(client, admin)
    for url in [f"/e/demo/screens/{screen.pk}/", f"/e/demo/screens/groups/{group.pk}/", "/screens/pair/",
                f"/e/demo/screens/?group={group.pk}"]:
        assert audit_url(client, url) == [], url


@pytest.mark.django_db
def test_tasks(event):
    from apps.screens import tasks

    assert tasks.sweep_health() == 0 and tasks.purge_pairing_requests() == 0
