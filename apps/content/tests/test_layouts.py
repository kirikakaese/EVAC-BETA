# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt
import io
import json
import re
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken
from apps.content import files, layout_format, layout_views, services
from apps.content.models import FontFamily, Layout, Theme
from apps.core.a11y import audit_url
from apps.core.models import AuditLog
from apps.events import services as event_services
from apps.screens import services as screen_services
from conftest import login_2fa


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def image(admin, event, django_capture_on_commit_callbacks):
    buf = io.BytesIO()
    Image.new("RGB", (64, 32), (255, 0, 0)).save(buf, "PNG")
    with django_capture_on_commit_callbacks(execute=True):
        asset, _ = services.upload_asset(event, SimpleUploadedFile("red.png", buf.getvalue()), actor=admin)
    asset.refresh_from_db()
    return asset


@pytest.fixture
def layout(admin, event):
    return services.create_layout(event, name="Foyer", key="foyer", actor=admin)


def screen_token(client, admin, event):
    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    screen = screen_services.pair(event, data["code"], actor=admin, name="S1")
    token = client.post(f"/player/api/pair/{data['id']}/", HTTP_X_PAIRING_SECRET=data["secret"]).json()["token"]
    return screen, token


def test_format_validation():
    assert layout_format.validate(layout_format.starter()) == []
    assert layout_format.validate(layout_format.empty(1080, 1920)) == []
    bad = layout_format.starter()
    bad["elements"].append(dict(bad["elements"][0]))
    assert "unique" in " ".join(layout_format.validate(bad))
    for broken in [
        {"format": 2, "width": 10, "height": 10, "elements": []},
        {**layout_format.empty(), "elements": [{"id": "x", "type": "script",
                                                "frame": {"x": 0, "y": 0, "w": 1, "h": 1}}]},
        {**layout_format.empty(), "elements": [{"id": "x", "type": "text", "frame": {"x": 0, "y": 0, "w": 1, "h": 1},
                                                "style": {"color": "red; background:url(x)"}}]},
        {**layout_format.empty(), "elements": [{"id": "x", "type": "text", "frame": {"x": 0, "y": 0, "w": 1, "h": 1},
                                                "props": {"onclick": "x"}}]},
        {**layout_format.empty(), "extra": 1},
    ]:
        assert layout_format.validate(broken), broken


@pytest.mark.django_db
def test_save_versions_conflict_publish_rollback(admin, event, layout, image):
    assert layout.is_default and layout.version == 1 and layout.has_unpublished_changes
    data = json.loads(json.dumps(layout.data))
    data["elements"].append({"id": "img", "type": "image", "frame": {"x": 0, "y": 0, "w": 10, "h": 10},
                             "props": {"asset": str(image.pk)}})
    services.save_layout(layout, data, actor=admin, expected_version=1)
    assert layout.version == 2 and layout.versions.count() == 2
    with pytest.raises(services.Conflict):
        services.save_layout(layout, data, actor=admin, expected_version=1)
    other_event = event_services.create_event(name="Other", slug="other", user=admin, timezone="UTC",
                                              start_date=event.start_date, end_date=event.end_date)
    foreign = services.create_layout(other_event, name="X", key="x", actor=admin)
    with pytest.raises(ValidationError, match="unknown file"):
        services.save_layout(foreign, data, actor=admin)
    assert services.asset_usage(image) == ["Layout Foyer"]
    v = services.publish_layout(layout, actor=admin)
    assert v.number == 2 and layout.published == v and not layout.has_unpublished_changes
    later = timezone.now() + dt.timedelta(hours=1)
    services.save_layout(layout, layout_format.starter(), actor=admin)
    scheduled = services.publish_layout(layout, actor=admin, at=later)
    layout.refresh_from_db()
    assert scheduled.publish_at == later and layout.published.number == 2
    assert services.publish_due(now=later + dt.timedelta(seconds=1)) == 1
    layout.refresh_from_db()
    assert layout.published.number == 3
    services.rollback_layout(layout, layout.versions.get(number=2), actor=admin)
    assert layout.version == 4 and layout.data == data and layout.published.number == 3
    diff = layout_format.summary_diff(layout.versions.get(number=3).data, layout.versions.get(number=4).data)
    assert diff["added"] == ["image img"]
    assert {"layout.saved", "layout.published", "layout.publish_scheduled"} <= set(
        AuditLog.objects.values_list("action", flat=True))


@pytest.mark.django_db
def test_portal_pages_and_editor(client, admin, event, layout):
    login_2fa(client, admin)
    r = client.post("/e/demo/content/layouts/", {"new-name": "Stage", "new-size": "1080x1920", "new-starter": ""})
    stage = Layout.objects.get(name="Stage")
    assert r.status_code == 302 and r["Location"].endswith(f"/layouts/{stage.pk}/edit/")
    assert stage.data["width"] == 1080 and stage.data["elements"] == [] and not stage.is_default
    page = client.get(f"/e/demo/content/layouts/{layout.pk}/edit/").content.decode()
    assert "evac-layout-editor" in page and "/static/editor/editor.js?v=" in page and 'id="editor-config"' in page
    config = json.loads(re.search(r'<script id="editor-config" type="application/json">(.*?)</script>', page,
                                  re.S).group(1))
    assert config["layout"]["version"] == 1 and "text" in config["types"] and config["canPublish"]
    save = f"/e/demo/content/layouts/{layout.pk}/save/"
    data = layout_format.starter()
    data["elements"][0]["props"]["text"] = "Hello"
    ok = client.post(save, json.dumps({"data": data, "version": 1}), content_type="application/json")
    assert ok.json() == {"ok": True, "version": 2, "saved_at": ok.json()["saved_at"]}
    stale = client.post(save, json.dumps({"data": data, "version": 1}), content_type="application/json")
    assert stale.status_code == 409 and stale.json()["conflict"]
    bad = client.post(save, json.dumps({"data": {"format": 1}, "version": 2}), content_type="application/json")
    assert bad.status_code == 400 and bad.json()["errors"]
    pub = client.post(f"/e/demo/content/layouts/{layout.pk}/publish/")
    assert pub.json() == {"ok": True, "published": 2}
    detail = client.get(f"/e/demo/content/layouts/{layout.pk}/").content.decode()
    assert "v2" in detail and "Restore" in detail
    client.post(f"/e/demo/content/layouts/{stage.pk}/", {"action": "default"})
    assert Layout.objects.get(pk=stage.pk).is_default and not Layout.objects.get(pk=layout.pk).is_default
    for url in ["/e/demo/content/layouts/", f"/e/demo/content/layouts/{layout.pk}/",
                f"/e/demo/content/layouts/{layout.pk}/edit/"]:
        assert audit_url(client, url) == [], url
    client.post(f"/e/demo/content/layouts/{stage.pk}/", {"action": "delete"})
    assert not Layout.objects.filter(pk=stage.pk).exists()


@pytest.mark.django_db
def test_permissions(client, event, layout, user, role, admin):
    event_services.assign_role(event, user, role("viewer"))
    client.force_login(user)
    assert client.get(f"/e/demo/content/layouts/{layout.pk}/").status_code == 200
    assert client.get(f"/e/demo/content/layouts/{layout.pk}/edit/").status_code == 403
    assert client.post(f"/e/demo/content/layouts/{layout.pk}/publish/").status_code == 403
    assert client.post(f"/e/demo/content/layouts/{layout.pk}/", {"action": "publish"}).status_code == 403


@pytest.mark.django_db
def test_player_bundle_signed_files_and_offline_contract(client, admin, event, layout, image):
    data = json.loads(json.dumps(layout.data))
    data["elements"].append({"id": "img", "type": "image", "frame": {"x": 0, "y": 0, "w": 10, "h": 10},
                             "props": {"asset": str(image.pk)}, "style": {"fontFamily": str(
                                 FontFamily.objects.get(name="Inter").pk)}})
    services.save_layout(layout, data, actor=admin)
    screen, token = screen_token(client, admin, event)
    dev = APIClient()
    dev.credentials(HTTP_AUTHORIZATION=f"Screen {token}")
    empty = dev.get("/player/api/content/bundle/").json()["bundle"]
    assert empty["layouts"] == []  # nothing published yet
    services.publish_layout(layout, actor=admin)
    theme = Theme(event=event, key="t", name="T")
    services.save_theme(theme, actor=admin, tokens={"dark_primary": "#123456"})
    services.set_event_theme(event, theme, actor=admin)
    bundle = dev.get("/player/api/content/bundle/").json()["bundle"]
    assert [entry["key"] for entry in bundle["layouts"]] == ["foyer"] and bundle["layouts"][0]["default"]
    assert bundle["theme"]["variables"]["--evac-color-primary"] == "#123456"
    assert "inter-latin-wght" in bundle["fonts_css"]  # font used by an element is included
    entry = bundle["assets"][str(image.pk)]
    url = entry["urls"]["webp"]
    assert "?s=" in url and str(screen.pk) in url
    assert APIClient().get(url).status_code == 200  # signed: no header needed (img/video tags)
    assert APIClient().get(url.split("?")[0]).status_code == 401
    assert APIClient().get(url[:-3] + "abc").status_code == 401  # tampered signature
    screen_services.revoke(screen, actor=admin)
    assert APIClient().get(url).status_code == 401
    assert files.screen_from_signature("not-a-uuid.abc", image.sha256) is None


@pytest.mark.django_db
def test_api(admin, event, image):
    _tok, raw = ServiceToken.issue(name="t", owner=admin, scopes=["content:read", "content:write"],
                                   created_with_2fa=True)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    r = c.post("/api/v1/events/demo/layouts/", {"name": "Bar"}, format="json")
    assert r.status_code == 201 and r.json()["key"] == "bar" and r.json()["version"] == 1
    lid = r.json()["id"]
    data = layout_format.empty()
    data["elements"] = [{"id": "i", "type": "image", "frame": {"x": 0, "y": 0, "w": 5, "h": 5},
                         "props": {"asset": str(image.pk)}}]
    assert c.patch(f"/api/v1/events/demo/layouts/{lid}/", {"data": data, "version": 1}, format="json").json()[
        "version"] == 2
    assert c.patch(f"/api/v1/events/demo/layouts/{lid}/", {"data": data, "version": 1},
                   format="json").status_code == 400
    assert c.patch(f"/api/v1/events/demo/layouts/{lid}/", {"data": {"format": 1}}, format="json").status_code == 400
    assert c.post(f"/api/v1/events/demo/layouts/{lid}/publish/").json()["version"] == 2
    assert c.get(f"/api/v1/events/demo/layouts/{lid}/").json()["published_version"] == 2
    assert c.delete(f"/api/v1/events/demo/layouts/{lid}/").status_code == 204


def test_editor_strings_are_complete():
    """Every string the editor shows goes through the server's translation list."""
    src = Path(dj_settings.BASE_DIR, "frontend/src/editor/main.ts").read_text()
    used = set(re.findall(r'this\.t\("([^"]+)"\)', src))
    for mapping in re.findall(r"const (?:TYPE|TOKEN)_LABELS[^=]*=\s*\{(.*?)\};", src, re.S):
        used |= set(re.findall(r':\s*"([^"]+)"', mapping))
    used |= set(re.findall(r'(?:num|check|choice|colour|field|assetSelect)\("([^"]+)"', src))
    used |= {label for label in re.findall(r'\["[^"]*", "([^"]+)"\]', src)
             if label[:1].isupper() and not label.startswith("HH")}
    missing = sorted(used - set(layout_views.EDITOR_STRINGS))
    assert missing == []
