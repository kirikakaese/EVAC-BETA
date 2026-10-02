# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import override_settings

from apps.accounts.models import ServiceToken
from apps.core import early_access
from apps.core.a11y import check_html

GATE = override_settings(EVAC_EARLY_ACCESS_PASSWORD="open-sesame")


def unlock(client, pw="open-sesame", next_url="/"):
    return client.post("/early-access/", {"password": pw, "next": next_url})


@pytest.mark.django_db
def test_off_by_default(client, admin):
    assert not early_access.enabled()
    assert client.get("/early-access/").status_code == 302
    assert client.get("/accounts/login/").status_code == 200


@pytest.mark.django_db
@GATE
def test_first_run_wizard_is_protected(client):
    r = client.get("/")
    assert r.status_code == 302 and r["Location"].startswith("/early-access/")
    assert client.get("/setup/")["Location"].startswith("/early-access/")
    page = client.get("/early-access/?next=/setup/")
    assert page.status_code == 200 and check_html(page.content.decode()) == []
    r = unlock(client, "wrong")
    assert r.status_code == 401 and "not correct" in r.content.decode()
    r = unlock(client, next_url="/setup/")
    assert r["Location"] == "/setup/" and early_access.COOKIE in r.cookies
    assert r.cookies[early_access.COOKIE]["httponly"]
    assert client.get("/setup/").status_code == 200


@pytest.mark.django_db
@GATE
def test_api_and_exemptions(client, admin, event):
    assert client.get("/api/v1/health/").status_code == 401
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert client.get("/metrics").status_code == 200
    _tok, raw = ServiceToken.issue(name="t", owner=admin)
    assert client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {raw}").status_code == 200
    # a fake token is not a way around the gate: the API rejects it
    assert client.get("/api/v1/me/", HTTP_AUTHORIZATION="Bearer evac_fake").status_code == 401
    url = "/api/v1/extensions/webhooks/00000000-0000-0000-0000-000000000000/webhook/"
    assert client.post(url, b"{}", content_type="application/json").status_code == 404  # reached the view


@pytest.mark.django_db
@GATE
def test_password_change_and_next_safety(client, admin):
    unlock(client)
    assert client.get("/accounts/login/").status_code == 200
    with override_settings(EVAC_EARLY_ACCESS_PASSWORD="new-password"):
        assert client.get("/accounts/login/").status_code == 302
        r = unlock(client, "new-password", next_url="https://evil.example.org/")
        assert r["Location"] == "/"
    assert not early_access.cookie_valid("garbage")
    assert not early_access.cookie_valid(None)


@pytest.mark.django_db(transaction=True)
@GATE
def test_websocket_needs_gate_cookie(member, event):
    from evac.asgi import application

    async def connect(cookie: str):
        headers = [(b"origin", b"http://testserver"), (b"host", b"testserver")]
        if cookie:
            headers.append((b"cookie", cookie.encode()))
        comm = WebsocketCommunicator(application, "/ws/e/demo/", headers=headers)
        comm.scope["user"] = member
        ok, code = await comm.connect()
        await comm.disconnect()
        return ok, code

    ok, code = async_to_sync(connect)("")
    assert not ok and code == 4401
    ok, _ = async_to_sync(connect)(f"{early_access.COOKIE}={early_access.make_cookie_value()}")
    assert ok
