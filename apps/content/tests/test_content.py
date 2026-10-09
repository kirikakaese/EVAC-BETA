# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import json
import subprocess
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken
from apps.content import media, services, storage
from apps.content import tokens as tok
from apps.content.models import Asset, FontFamily, Theme
from apps.core import modules
from apps.core.a11y import audit_url
from apps.core.models import AuditLog
from apps.events import services as event_services
from conftest import login_2fa

FONT = Path(dj_settings.BASE_DIR) / "static/fonts/atkinson-hyperlegible/atkinson-hyperlegible-latin-700-normal.woff2"
INTER = Path(dj_settings.BASE_DIR) / "static/fonts/inter/inter-latin-wght-normal.woff2"
needs_ffmpeg = pytest.mark.skipif(not media.has_ffmpeg(), reason="ffmpeg not installed")


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def run_on_commit(django_capture_on_commit_callbacks):
    def upload(*args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return services.upload_asset(*args, **kwargs)
    return upload


def png(name="pic.png", size=(1200, 800), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def api(user, scopes=("content:read", "content:write")):
    _tok, raw = ServiceToken.issue(name="t", owner=user, scopes=list(scopes), created_with_2fa=True)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    return c


# --------------------------------------------------------------------------- tokens and themes

def test_css_variables():
    values = {k: p["default"] for k, p in tok.schema()["properties"].items()}
    values.update({"mode": "light", "background_type": "gradient", "logo": "a1", "font_body": "f1"})
    css = tok.css_variables(values, families={"f1": '"evac-x", sans-serif'}, urls={"a1": "/x.webp"})
    assert css["--evac-color-background"] == "#ffffff" and css["--evac-font-body"] == '"evac-x", sans-serif'
    assert css["--evac-background"].startswith("linear-gradient(160deg") and css["--evac-logo"] == 'url("/x.webp")'
    assert tok.css_block({"--a": "1", "--b": "x;}body{"}) == ":root{--a:1;}"


@pytest.mark.django_db
def test_theme_inheritance_locking_and_default(client, admin, event):
    login_2fa(client, admin)
    r = client.post("/e/demo/content/themes/", {"new-name": "Festival", "new-key": ""})
    base = Theme.objects.get(name="Festival")
    assert r.status_code == 302 and base.key == "festival"
    page = client.get(f"/e/demo/content/themes/{base.pk}/").content.decode()
    assert "Design tokens" in page and "--evac-color-primary" in page
    services.save_theme(base, actor=admin, tokens={"dark_primary": "#ff0000", "font_size_base": 4})
    child = Theme(event=event, key="stage", name="Stage", parent=base)
    services.save_theme(child, actor=admin, tokens={"dark_accent": "#00ff00"})
    resolved = child.resolved()
    assert resolved["dark_primary"] == "#ff0000" and resolved["dark_accent"] == "#00ff00"
    assert resolved["mode"] == "dark"
    data = {"meta-name": "Stage", "meta-key": "stage", "meta-parent": str(base.pk), "version": child.version,
            "tok-dark_text": "#123456"}
    for name in tok.schema()["properties"]:
        if name != "dark_text":
            data[f"tok-{name}__inherit"] = "on"
    assert client.post(f"/e/demo/content/themes/{child.pk}/", data).status_code == 302
    child.refresh_from_db()
    assert child.tokens == {"dark_text": "#123456"} and child.version == 2
    r = client.post(f"/e/demo/content/themes/{child.pk}/", data, follow=True)  # stale version
    assert "Someone else saved this theme" in r.content.decode()
    client.post(f"/e/demo/content/themes/{child.pk}/", {"action": "default"})
    event.refresh_from_db()
    assert event.default_theme == "stage" and services.event_theme(event) == child
    r = client.post(f"/e/demo/content/themes/{base.pk}/", {"action": "delete"}, follow=True)
    assert "inherit from this theme" in r.content.decode() and Theme.objects.filter(pk=base.pk).exists()
    with pytest.raises(ValidationError, match="inherit from itself"):
        base.parent = child
        services.save_theme(base, actor=admin)


# --------------------------------------------------------------------------- fonts

@pytest.mark.django_db
def test_font_upload_and_css(client, admin, event, media_root):
    assert FontFamily.objects.filter(builtin=True).count() == 2
    login_2fa(client, admin)
    up = SimpleUploadedFile("Atkinson-Bold.woff2", FONT.read_bytes())
    r = client.post("/e/demo/content/fonts/", {"font-file": up, "font-name": "House font", "font-category": "sans",
                                               "font-licence": "OFL"})
    assert r.status_code == 302
    fam = FontFamily.objects.get(name="House font")
    ff = fam.files.get()
    assert ff.weight_min == 700 and ff.style == "normal" and storage.path(ff.sha256, "font.woff2").exists()
    var = services.upload_font(event, SimpleUploadedFile("inter.woff2", INTER.read_bytes()), actor=admin,
                               subset=True)
    assert var.is_variable and var.weight_min == 100 and var.weight_max == 900 and var.unicode_range
    css = client.get("/e/demo/content/fonts.css").content.decode()
    assert f'font-family:"{fam.css_family}"' in css and "/static/fonts/atkinson-hyperlegible/" in css
    assert "font-weight:100 900" in css
    font_url = f"/content/files/{ff.sha256}/font.woff2"
    assert font_url in css and client.get(font_url)["Content-Type"] == "font/woff2"
    bad = SimpleUploadedFile("x.ttf", b"not a font")
    r = client.post("/e/demo/content/fonts/", {"font-file": bad, "font-category": "sans"})
    assert "not a readable font" in r.content.decode()
    client.post(f"/e/demo/content/fonts/{fam.pk}/delete/")
    assert not FontFamily.objects.filter(pk=fam.pk).exists() and not storage.directory(ff.sha256).exists()
    builtin = FontFamily.objects.filter(builtin=True).first()
    client.post(f"/e/demo/content/fonts/{builtin.pk}/delete/")
    assert FontFamily.objects.filter(pk=builtin.pk).exists()


# --------------------------------------------------------------------------- assets

@pytest.mark.django_db
def test_image_upload_variants_and_dedupe(client, admin, event, run_on_commit):
    asset, created = run_on_commit(event, png(), actor=admin, tags="Foyer, Logo")
    asset.refresh_from_db()
    assert created and asset.status == "ready" and asset.width == 1200 and asset.tags == ["foyer", "logo"]
    assert {"original", "thumb", "webp", "avif"} <= set(asset.variants)
    with Image.open(storage.path(asset.sha256, "thumb.webp")) as im:
        assert max(im.size) == 480
    again, created = run_on_commit(event, png(), actor=admin)
    assert again == asset and not created
    login_2fa(client, admin)
    page = client.get("/e/demo/content/assets/").content.decode()
    assert f"/content/files/{asset.sha256}/thumb.webp" in page
    r = client.get(f"/content/files/{asset.sha256}/image.webp")
    assert r["Content-Type"] == "image/webp" and "immutable" in r["Cache-Control"]
    assert client.get(f"/content/files/{asset.sha256}/secret.txt").status_code == 404
    assert client.get(f"/e/demo/content/assets/{asset.pk}/").status_code == 200
    client.post(f"/e/demo/content/assets/{asset.pk}/", {"asset-name": "Logo", "asset-alt_text": "EVAC logo",
                                                         "asset-tags": "logo"})
    asset.refresh_from_db()
    assert asset.alt_text == "EVAC logo" and AuditLog.objects.filter(action="asset.updated").exists()


@pytest.mark.django_db
def test_exif_rotation_and_metadata_stripped(admin, event, run_on_commit):
    im = Image.new("RGB", (400, 200), (0, 0, 255))
    exif = im.getexif()
    exif[0x0112] = 6  # rotate 90 degrees
    exif[0x010F] = "SecretCam"  # make: metadata that must not survive
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    asset, _ = run_on_commit(event, SimpleUploadedFile("photo.jpg", buf.getvalue()), actor=admin)
    asset.refresh_from_db()
    with Image.open(storage.path(asset.sha256, "image.webp")) as out:
        assert out.size == (200, 400) and not out.getexif()


@pytest.mark.django_db
def test_svg_is_sanitised(admin, event, run_on_commit):
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" onload="alert(1)">'
           b'<script>alert(2)</script><foreignObject><p>x</p></foreignObject>'
           b'<image xlink:href="https://evil.example/x.png"/><a href="javascript:alert(3)"><rect width="5" '
           b'height="5" style="fill:url(https://evil.example/f)"/></a><use href="#ok"/>'
           b'<style>@import url(https://evil.example/s.css);</style></svg>')
    asset, _ = run_on_commit(event, SimpleUploadedFile("icon.svg", svg), actor=admin)
    clean = storage.path(asset.sha256, "original.svg").read_bytes()
    for bad in (b"onload", b"<script", b"foreignObject", b"evil.example", b"javascript:"):
        assert bad not in clean, bad
    assert b'href="#ok"' in clean


@pytest.mark.django_db
def test_rejected_uploads(admin, event, settings):
    with pytest.raises(Exception, match="not supported"):
        services.upload_asset(event, SimpleUploadedFile("x.exe", b"MZ"), actor=admin)
    with pytest.raises(Exception, match="not a valid image"):
        services.upload_asset(event, SimpleUploadedFile("fake.png", b"<html>"), actor=admin)
    with pytest.raises(Exception, match="not a PDF"):
        services.upload_asset(event, SimpleUploadedFile("doc.pdf", b"hello"), actor=admin)
    with pytest.raises(Exception, match="Lottie"):
        services.upload_asset(event, SimpleUploadedFile("anim.json", b'{"a": 1}'), actor=admin)
    with pytest.raises(Exception, match="billion|not a valid SVG"):
        services.upload_asset(event, SimpleUploadedFile("bomb.svg", b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a '
                                                        b'"aaaa"><!ENTITY b "&a;&a;">]><svg>&b;</svg>'), actor=admin)
    from apps.core import settings_store

    settings_store.save("content", "event", str(event.pk), {"max_upload_mb": 1}, user=admin, event=event)
    with pytest.raises(Exception, match="at most 1 MB"):
        services.upload_asset(event, SimpleUploadedFile("big.pdf", b"%PDF-" + b"0" * 2_000_000), actor=admin)
    assert Asset.objects.count() == 0


@pytest.mark.django_db
def test_pdf_and_lottie(admin, event, run_on_commit):
    pdf, _ = run_on_commit(event, SimpleUploadedFile("plan.pdf", b"%PDF-1.4\n%%EOF"), actor=admin)
    lottie = {"v": "5.7", "fr": 30, "ip": 0, "op": 60, "w": 512, "h": 512, "layers": []}
    anim, _ = run_on_commit(event, SimpleUploadedFile("anim.json", json.dumps(lottie).encode()), actor=admin)
    pdf.refresh_from_db()
    anim.refresh_from_db()
    assert pdf.status == "ready" and anim.kind == "lottie" and anim.duration == 2 and anim.width == 512


@needs_ffmpeg
@pytest.mark.django_db
def test_video_and_audio_transcoding(admin, event, run_on_commit, tmp_path):
    video = tmp_path / "clip.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", "-c:v", "libx264",
                    "-c:a", "aac", str(video)], check=True)
    asset, _ = run_on_commit(event, SimpleUploadedFile("clip.mov", video.read_bytes()), actor=admin)
    asset.refresh_from_db()
    assert asset.status == "ready", asset.note
    assert {"poster", "thumb", "mp4", "webm"} <= set(asset.variants) and asset.width == 320
    assert round(asset.duration) == 2
    audio = tmp_path / "gong.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=660:duration=1", str(audio)],
                   check=True)
    sound, _ = run_on_commit(event, SimpleUploadedFile("gong.wav", audio.read_bytes()), actor=admin)
    sound.refresh_from_db()
    assert sound.status == "ready" and "audio" in sound.variants
    other = tmp_path / "beep.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=880:duration=1", str(other)],
                   check=True)
    with pytest.raises(Exception, match="no video"):
        services.upload_asset(event, SimpleUploadedFile("sound.mp4", other.read_bytes()), actor=admin)


@pytest.mark.django_db
def test_without_ffmpeg_files_are_kept(admin, event, run_on_commit, monkeypatch):
    monkeypatch.setattr(media, "has_ffmpeg", lambda: False)
    asset, _ = run_on_commit(event, SimpleUploadedFile("clip.mp4", b"\x00\x00\x00\x18ftypmp42"), actor=admin)
    asset.refresh_from_db()
    assert asset.status == "ready" and "ffmpeg is not installed" in asset.note and set(asset.variants) == {"original"}


@pytest.mark.django_db
def test_usage_blocks_delete_and_gc(client, admin, event, run_on_commit):
    asset, _ = run_on_commit(event, png(), actor=admin)
    theme = Theme(event=event, key="t", name="T")
    services.save_theme(theme, actor=admin, tokens={"logo": str(asset.pk)}, schema=services.theme_schema(event))
    assert services.asset_usage(asset) == ["Theme T"]
    login_2fa(client, admin)
    r = client.post(f"/e/demo/content/assets/{asset.pk}/", {"action": "delete"}, follow=True)
    assert "still used" in r.content.decode()
    services.save_theme(theme, actor=admin, tokens={})
    client.post(f"/e/demo/content/assets/{asset.pk}/", {"action": "delete"})
    assert not Asset.objects.exists() and not storage.directory(asset.sha256).exists()


@pytest.mark.django_db
def test_file_access_rules(client, admin, event, user, other, run_on_commit, role):
    asset, _ = run_on_commit(event, png(), actor=admin)
    url = f"/content/files/{asset.sha256}/thumb.webp"
    assert client.get(url).status_code == 302  # login
    client.force_login(other)
    assert client.get(url).status_code == 404  # not a member
    event_services.assign_role(event, user, role("viewer"))
    client.force_login(user)
    assert client.get(url).status_code == 200
    shared, _ = run_on_commit(None, png("shared.png", color=(1, 2, 3)), actor=admin)
    assert client.get(f"/content/files/{shared.sha256}/thumb.webp").status_code == 200
    client.force_login(other)
    assert client.get(f"/content/files/{shared.sha256}/thumb.webp").status_code == 404
    # viewers cannot upload or change shared items
    client.force_login(user)
    assert client.post("/e/demo/content/assets/", {"up-files": png()}).status_code == 403


@pytest.mark.django_db
def test_player_theme_and_files(client, admin, event, run_on_commit):
    from apps.screens import services as screen_services

    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    screen_services.pair(event, data["code"], actor=admin)
    token = client.post(f"/player/api/pair/{data['id']}/", HTTP_X_PAIRING_SECRET=data["secret"]).json()["token"]
    asset, _ = run_on_commit(event, png(), actor=admin)
    theme = Theme(event=event, key="t", name="T")
    services.save_theme(theme, actor=admin, tokens={"logo": str(asset.pk), "dark_primary": "#ff00aa"},
                        schema=services.theme_schema(event))
    services.set_event_theme(event, theme, actor=admin)
    dev = APIClient()
    dev.credentials(HTTP_AUTHORIZATION=f"Screen {token}")
    payload = dev.get("/player/api/content/theme/").json()["theme"]
    assert payload["key"] == "t" and payload["variables"]["--evac-color-primary"] == "#ff00aa"
    logo = payload["variables"]["--evac-logo"]
    assert f"/player/api/content/files/{asset.sha256}/image.webp" in logo
    assert dev.get(f"/player/api/content/files/{asset.sha256}/image.webp").status_code == 200
    other_event = event_services.create_event(name="Other", slug="other", user=admin, timezone="UTC",
                                              start_date=event.start_date, end_date=event.end_date)
    foreign, _ = run_on_commit(other_event, png("o.png", color=(9, 9, 9)), actor=admin)
    assert dev.get(f"/player/api/content/files/{foreign.sha256}/image.webp").status_code == 404
    assert APIClient().get("/player/api/content/theme/").status_code == 401
    msgs = dev.get("/player/api/poll/?since=0&wait=0").json()["messages"]
    assert "config.changed" in [m["type"] for m in msgs]


@pytest.mark.django_db
def test_api(admin, event, run_on_commit):
    c = api(admin)
    up = c.post("/api/v1/events/demo/assets/", {"upload": png(), "name": "Red"}, format="multipart")
    assert up.status_code == 201, up.json() and up.json()["kind"] == "image"
    assert c.get("/api/v1/events/demo/assets/?kind=image").json()["count"] == 1
    aid = up.json()["id"]
    assert c.patch(f"/api/v1/events/demo/assets/{aid}/", {"alt_text": "Red"}, format="json").json()["alt_text"] == "Red"
    t = c.post("/api/v1/events/demo/themes/", {"key": "x", "name": "X", "tokens": {"mode": "light"}}, format="json")
    assert t.status_code == 201 and t.json()["resolved"]["mode"] == "light"
    bad = c.patch(f"/api/v1/events/demo/themes/{t.json()['id']}/", {"tokens": {"mode": "pink"}}, format="json")
    assert bad.status_code == 400
    stale = c.patch(f"/api/v1/events/demo/themes/{t.json()['id']}/", {"name": "Y", "version": 99}, format="json")
    assert stale.status_code == 400
    f = c.post("/api/v1/events/demo/fonts/", {"upload": SimpleUploadedFile("a.woff2", FONT.read_bytes())},
               format="multipart")
    assert f.status_code == 201 and f.json()["files"][0]["weight_min"] == 700
    ro = api(admin, ("content:read",))
    assert ro.post("/api/v1/events/demo/themes/", {"key": "z", "name": "Z"}, format="json").status_code == 403
    assert c.delete(f"/api/v1/events/demo/assets/{aid}/").status_code == 204
    modules.set_event(event, "content", False)
    assert c.get("/api/v1/events/demo/assets/").status_code == 404


@pytest.mark.django_db
def test_module_depends_on_screens(client, admin, event):
    login_2fa(client, admin)
    assert client.get("/e/demo/content/").status_code == 200
    modules.set_event(event, "screens", False)
    assert client.get("/e/demo/content/").status_code == 404


@pytest.mark.django_db
def test_pages_accessible(client, admin, event, run_on_commit):
    asset, _ = run_on_commit(event, png(), actor=admin)
    theme = Theme(event=event, key="t", name="T")
    services.save_theme(theme, actor=admin)
    login_2fa(client, admin)
    for url in ["/e/demo/content/", "/e/demo/content/themes/", f"/e/demo/content/themes/{theme.pk}/",
                "/e/demo/content/fonts/", "/e/demo/content/assets/", f"/e/demo/content/assets/{asset.pk}/"]:
        assert audit_url(client, url) == [], url


def test_storage_rejects_traversal():
    with pytest.raises(ValueError):
        storage.path("a" * 64, "../etc/passwd")
    with pytest.raises(ValueError):
        storage.directory("../../x")


