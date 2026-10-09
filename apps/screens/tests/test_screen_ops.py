# SPDX-License-Identifier: AGPL-3.0-or-later
"""Display settings, remote management, the welcome slide and the wizard's pairing step."""
import io
import json

import pytest
from django.core.cache import cache
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.content.models import Layout
from apps.core import settings_store
from apps.core.a11y import audit_url
from apps.events.models import Event
from apps.screens import channel, display, remote, services
from apps.screens.models import ScreenGroup
from conftest import login_2fa


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


def pair(client, admin, event, name="Foyer"):
    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    screen = services.pair(event, data["code"], actor=admin, name=name)
    token = client.post(f"/player/api/pair/{data['id']}/", HTTP_X_PAIRING_SECRET=data["secret"]).json()["token"]
    return screen, token


def device(token):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Screen {token}")
    return c


def jpeg(w=2400, h=1350):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 200, 30)).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.django_db
def test_display_settings_inherit_through_groups(client, admin, event, django_capture_on_commit_callbacks):
    screen, token = pair(client, admin, event)
    a = ScreenGroup.objects.create(event=event, name="A stage")
    b = ScreenGroup.objects.create(event=event, name="B portrait")
    screen.manual_groups.add(a, b)
    settings_store.save("display", "event", str(event.pk), {"volume": 50, "dim_level": 30}, user=admin, event=event)
    settings_store.save("display", "screen_group", str(a.pk), {"rotation": "180", "volume": 20}, user=admin,
                        event=event)
    seq = channel.last_seq(screen.pk)
    with django_capture_on_commit_callbacks(execute=True):
        settings_store.save("display", "screen_group", str(b.pk), {"rotation": "90"}, user=admin, event=event)
    assert channel.last_seq(screen.pk) == seq + 1  # the screen was told to reload its configuration
    with django_capture_on_commit_callbacks(execute=True):
        settings_store.save("display", "screen", str(screen.pk), {"overscan": 3}, user=admin, event=event)
    resolved = display.resolve(screen)
    assert resolved.values["rotation"] == "90"  # B comes after A
    assert resolved.values["volume"] == 20 and resolved.values["dim_level"] == 30 and resolved.values["overscan"] == 3
    assert resolved.source["overscan"] == "screen" and resolved.source["volume"] == "screen_group"
    cfg = device(token).get("/player/api/config/").json()
    assert cfg["display"]["rotation"] == "90" and cfg["display"]["daily_reload"] == "04:00"
    # instance-level change reaches every screen; other namespaces do not notify
    seq = channel.last_seq(screen.pk)
    with django_capture_on_commit_callbacks(execute=True):
        settings_store.save("display", "instance", "", {"audio": False}, user=admin)
        settings_store.save("content", "instance", "", {"avif": False}, user=admin)
    assert channel.last_seq(screen.pk) == seq + 1


@pytest.mark.django_db
def test_display_pages(client, admin, event):
    screen, _token = pair(client, admin, event)
    group = ScreenGroup.objects.create(event=event, name="Stage")
    login_2fa(client, admin)
    url = f"/e/demo/screens/{screen.pk}/display/"
    page = client.get(url).content.decode()
    assert "Rotation" in page and "Daily reload" in page
    form = {"rotation": "270", "overscan": 2, "scale": 100, "keystone_x": 0, "keystone_y": 0, "dim_level": 40,
            "volume": 80, "daily_reload": "04:00", "evacuation_role": "participant", "audio": "on"}
    inherit = {f"{k}__inherit": "on" for k in display.SCHEMA["properties"] if k not in ("rotation", "overscan")}
    r = client.post(url, {**form, **inherit})
    assert r.status_code == 302
    assert settings_store.raw("display", "screen", str(screen.pk)) == {"rotation": "270", "overscan": 2}
    bad = client.post(url, {**form, "dim_from": "25:99"})
    assert bad.status_code == 200 and not settings_store.raw("display", "screen", str(screen.pk)).get("dim_from")
    gurl = f"/e/demo/screens/groups/{group.pk}/display/"
    assert client.post(gurl, {**form, **inherit, "rotation": "90"}).status_code == 302
    assert settings_store.raw("display", "screen_group", str(group.pk)) == {"rotation": "90", "overscan": 2}
    for u in (url, gurl, f"/e/demo/screens/{screen.pk}/", f"/e/demo/screens/groups/{group.pk}/"):
        assert audit_url(client, u) == [], u


@pytest.mark.django_db
def test_remote_management(client, admin, event):
    screen, token = pair(client, admin, event)
    dev = device(token)
    # nothing requested: uploads are refused
    assert dev.post("/player/api/upload/screenshot/", jpeg(), content_type="image/png").status_code == 409
    assert dev.post("/player/api/upload/logs/", {"lines": ["x"]}, format="json").status_code == 409
    assert dev.post("/player/api/upload/other/", {}, format="json").status_code == 404
    assert APIClient().post("/player/api/upload/logs/", {}, format="json").status_code == 401
    login_2fa(client, admin)
    for name in ("screenshot", "logs", "test_pattern", "clear_cache"):
        r = client.post(f"/e/demo/screens/{screen.pk}/command/{name}/")
        assert r.status_code == 302 and r.url.endswith("#remote")
    sent = [m["type"] for m in channel.since(screen.pk, 0)]
    assert {"screenshot", "logs", "test_pattern", "clear_cache"} <= set(sent)
    assert client.post(f"/e/demo/screens/{screen.pk}/command/format_disk/").status_code == 403
    panel = client.get(f"/e/demo/screens/{screen.pk}/remote/").content.decode()
    assert 'hx-trigger="every 2s"' in panel and "Waiting for the screen" in panel
    # garbage is refused, a real image is re-encoded and down-scaled
    assert dev.post("/player/api/upload/screenshot/", b"<svg/>", content_type="image/svg+xml").status_code == 409
    assert dev.post("/player/api/upload/screenshot/", jpeg(), content_type="image/png").status_code == 200
    stored = Image.open(remote.screenshot_path(screen))
    assert stored.format == "JPEG" and stored.width == 1920
    shot = client.get(f"/e/demo/screens/{screen.pk}/screenshot.jpg")
    assert shot.status_code == 200 and shot["Content-Type"] == "image/jpeg" and "no-store" in shot["Cache-Control"]
    # one upload per request
    assert dev.post("/player/api/upload/screenshot/", jpeg(), content_type="image/png").status_code == 409
    lines = [f"line {n}" for n in range(500)] + ["x" * 900]
    assert dev.post("/player/api/upload/logs/", {"lines": lines}, format="json").status_code == 200
    screen.refresh_from_db()
    assert len(screen.logs) == 300 and len(screen.logs[-1]) == 500 and screen.logs_at
    # a screen that cannot capture says so
    services.command(screen, "screenshot", actor=admin)
    r = dev.post("/player/api/upload/screenshot/", json.dumps({"error": "NotAllowedError"}),
                 content_type="application/json")
    assert r.status_code == 200
    screen.refresh_from_db()
    assert screen.screenshot_error == "NotAllowedError"
    page = client.get(f"/e/demo/screens/{screen.pk}/").content.decode()
    assert "could not take a screenshot" in page and "line 499" in page and "screenshot.jpg" in page
    assert audit_url(client, f"/e/demo/screens/{screen.pk}/") == []
    services.command(screen, "logs", actor=admin)
    assert dev.post("/player/api/upload/logs/", {"lines": "nope"}, format="json").status_code == 409
    services.delete_screen(screen, actor=admin)
    assert not remote.screenshot_path(screen).exists()
    cache.clear()


@pytest.mark.django_db
def test_resolution_mismatch_and_reported_keys(client, admin, event):
    screen, token = pair(client, admin, event)
    settings_store.save("display", "screen", str(screen.pk), {"expected_resolution": "3840x2160"}, user=admin,
                        event=event)
    device(token).post("/player/api/heartbeat/", {"data": {"resolution": "1920x1080", "display_state": "dimmed",
                                                           "capture": True, "recovered": "restarted"}}, format="json")
    screen.refresh_from_db()
    assert screen.reported["display_state"] == "dimmed" and screen.reported["capture"] is True
    login_2fa(client, admin)
    assert "expected 3840x2160" in client.get(f"/e/demo/screens/{screen.pk}/").content.decode()


@pytest.mark.django_db
def test_welcome_slide_on_first_pairing(client, admin, event):
    assert not Layout.objects.filter(event=event).exists()
    pair(client, admin, event)
    welcome = Layout.objects.get(event=event)
    assert welcome.key == "welcome" and welcome.is_default and welcome.published_id
    pair(client, admin, event, name="Second")
    assert Layout.objects.filter(event=event).count() == 1


@pytest.mark.django_db
def test_wizard_pairs_the_first_screen(client):
    client.post("/setup/", {"email": "boss@example.org", "display_name": "Boss", "password1": "a-good-password-9",
                            "password2": "a-good-password-9"})
    client.post("/setup/?step=venue", {"skip": "1"})
    client.post("/setup/?step=event", {"name": "Spring Fair", "slug": "spring", "timezone": "Europe/Berlin"})
    page = client.get("/setup/?step=screen").content.decode()
    assert "/player/" in page and 'name="code"' in page
    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    r = client.post("/setup/?step=screen", {"code": data["code"], "name": "Entrance"})
    assert r.status_code == 302 and r.url.startswith("/e/spring/screens/pair/?code=")
    form = client.get(r.url).content.decode()
    assert 'value="Entrance"' in form and 'name="next"' in form
    r = client.post(r.url, {"code": data["code"], "name": "Entrance", "next": "/setup/?step=done"})
    assert r.status_code == 302 and r.url == "/setup/?step=done"
    event = Event.objects.get(slug="spring")
    assert event.screens.get().name == "Entrance"
    assert Layout.objects.get(event=event).key == "welcome"
    assert "All set" in client.get(r.url).content.decode()
    # an unsafe next is ignored
    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    r = client.post("/e/spring/screens/pair/", {"code": data["code"], "name": "X", "next": "https://evil.example/"})
    assert r.url.startswith("/e/spring/screens/")
    assert User.objects.count() == 1
