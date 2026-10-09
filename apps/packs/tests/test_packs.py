# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt
import io
import json
import socket
import zipfile
from unittest import mock

import pytest
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from PIL import Image

from apps.accounts.models import User
from apps.content import services as content_services
from apps.content.models import Asset, FontFamily, Layout, Theme
from apps.core import modules, settings_store
from apps.core.a11y import audit_url
from apps.core.models import AuditLog
from apps.events import services as event_services
from apps.packs import engine, gallery, packfile, services
from apps.packs.models import PackImport, TrustedKey
from apps.playlists import services as playlist_services
from apps.playlists.models import Playlist, PlaylistItem
from apps.widgets import services as widget_services
from apps.widgets.models import CustomWidget, Feed
from conftest import login_2fa

PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def target(db, admin):
    return event_services.create_event(name="Other Fest", slug="other", user=admin, timezone="Europe/Berlin",
                                       start_date=dt.date(2026, 8, 1), end_date=dt.date(2026, 8, 2))


def _png(colour=(200, 30, 30)) -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), colour).save(buf, "PNG")
    return SimpleUploadedFile("logo.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def content(event, admin):
    """A playlist with a layout that uses a picture, a built-in font, a theme (with a parent) and a widget."""
    asset, _ = content_services.upload_asset(event, _png(), actor=admin, name="Logo")
    content_services.process(asset)
    inter = FontFamily.objects.get(builtin=True, name="Inter")
    base = content_services.save_theme(Theme(event=event, key="base", name="Base"), actor=admin,
                                       tokens={"dark_accent": "#ff0000"})
    theme = content_services.save_theme(Theme(event=event, key="stage", name="Stage", parent=base), actor=admin,
                                        tokens={"logo": str(asset.pk), "font_heading": str(inter.pk)},
                                        schema=content_services.theme_schema(event))
    feed = widget_services.save_feed(Feed(event=event, name="Info", kind=Feed.Kind.SOURCE, source="event.info"),
                                     actor=admin)
    widget = widget_services.save_widget(CustomWidget(event=event, name="Venues", feed=feed, items_path="$.venues",
                                                      fields={"title": "name"}), actor=admin)
    data = {"format": 1, "width": 1920, "height": 1080, "background": {"color": "token:background"}, "elements": [
        {"id": "pic", "type": "image", "name": "Logo", "frame": {"x": 1, "y": 1, "w": 20, "h": 20}, "style": {},
         "props": {"asset": str(asset.pk), "fit": "contain"}},
        {"id": "t", "type": "text", "name": "Title", "frame": {"x": 30, "y": 1, "w": 60, "h": 20},
         "style": {"fontFamily": str(inter.pk)}, "props": {"text": "{{ event.name }}"}},
        {"id": "d", "type": "data", "name": "Venues", "frame": {"x": 1, "y": 30, "w": 90, "h": 60}, "style": {},
         "props": {"widget": str(widget.pk)}}]}
    layout = content_services.create_layout(event, name="Stage", key="stage", actor=admin, data=data)
    layout.theme = theme
    layout.save()
    content_services.publish_layout(layout, actor=admin)
    pl = playlist_services.save_playlist(Playlist(event=event, name="Main loop", default_duration=12), actor=admin)
    playlist_services.save_item(PlaylistItem(playlist=pl, layout=layout, weight=2, tags=["foyer"]), actor=admin)
    return {"asset": asset, "theme": theme, "base": base, "feed": feed, "widget": widget, "layout": layout,
            "playlist": pl, "inter": inter}


def _export(event, admin, selection, **kw) -> bytes:
    return services.export(event, selection, name=kw.pop("name", "Test pack"), actor=admin, **kw).read()


def _stage(event, admin, data: bytes, name="test.evacpack") -> PackImport:
    return services.stage_upload(event, SimpleUploadedFile(name, data), actor=admin)


# ------------------------------------------------------------------ file format
def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _manifest(**kw) -> dict:
    return {"format": "evacpack", "version": 1, "name": "x", "sections": {}, "files": {}, **kw}


def test_packfile_roundtrip_and_tampering():
    key = Ed25519PrivateKey.generate()
    files = packfile.FileSet()
    ref = files.add(b"hello", "a/b/hello.txt")
    assert files.add(b"hello", "other.txt") == ref  # same content packed once
    out = io.BytesIO()
    manifest = packfile.write(out, name="P", description="d", sections={"layouts": [{"id": "1", "file": ref}]},
                              files=files, modules=["content", "content"], generator="EVAC test",
                              signer=(key, "Test signer"))
    assert manifest["files"][ref] == {"name": "hello.txt", "size": 5} and manifest["modules"] == ["content"]
    data = out.getvalue()
    pack = packfile.read(data, max_bytes=1000)
    assert pack.signed and pack.signer == "Test signer" and pack.sections["layouts"][0]["id"] == "1"
    assert len(packfile.fingerprint(pack.public_key).split()) == 8 and packfile.fingerprint("!!") == "?"

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = {n: zf.read(n) for n in zf.namelist()}
    changed = json.loads(entries["manifest.json"])
    changed["name"] = "Evil"
    with pytest.raises(packfile.PackError, match="signature does not match"):
        packfile.read(_zip({**entries, "manifest.json": json.dumps(changed).encode()}), max_bytes=1000)
    with pytest.raises(packfile.PackError, match="damaged"):
        packfile.read(_zip({**entries, f"files/{ref}": b"HELLO"}), max_bytes=1000)
    with pytest.raises(packfile.PackError, match="Unexpected entry"):
        packfile.read(_zip({**entries, "../evil.sh": b"x"}), max_bytes=1000)
    with pytest.raises(packfile.PackError, match="do not match"):
        packfile.read(_zip({k: v for k, v in entries.items() if not k.startswith("files/")}), max_bytes=1000)
    with pytest.raises(packfile.PackError, match="larger"):
        packfile.read(data, max_bytes=3)
    with pytest.raises(packfile.PackError, match="malformed"):
        packfile.read(_zip({**entries, "signature.json": b'{"algorithm": "Ed25519"}'}), max_bytes=1000)
    sig = json.loads(entries["signature.json"])
    with pytest.raises(packfile.PackError, match="algorithm"):
        packfile.read(_zip({**entries, "signature.json": json.dumps({**sig, "algorithm": "RSA"}).encode()}),
                      max_bytes=1000)
    unsigned = _zip({k: v for k, v in entries.items() if k != "signature.json"})
    assert not packfile.read(unsigned, max_bytes=1000).signed


@pytest.mark.parametrize("data,message", [
    (b"not a zip", "not a zip"),
    (_zip({"other.json": b"{}"}), "Unexpected entry"),
    (_zip({"signature.json": b"{}"}), "manifest.json missing"),
    (_zip({"manifest.json": b"nope"}), "not valid JSON"),
    (_zip({"manifest.json": json.dumps({"format": "zip"}).encode()}), "wrong format"),
    (_zip({"manifest.json": json.dumps(_manifest(version=9)).encode()}), "version 9"),
    (_zip({"manifest.json": json.dumps(_manifest(sections=[])).encode()}), "incomplete"),
    (_zip({"manifest.json": json.dumps(_manifest(sections={"layouts": [{"no": "id"}]})).encode()}), "malformed"),
])
def test_packfile_rejects(data, message):
    with pytest.raises(packfile.PackError, match=message):
        packfile.read(data, max_bytes=1000)


def test_packfile_duplicate_entries():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf, pytest.warns(UserWarning):
        zf.writestr("manifest.json", json.dumps(_manifest()))
        zf.writestr("manifest.json", json.dumps(_manifest(name="second")))
    with pytest.raises(packfile.PackError, match="twice"):
        packfile.read(buf.getvalue(), max_bytes=1000)


# ------------------------------------------------------------------ export and import
def test_export_includes_dependencies(event, admin, content):
    sections, files, mods = engine.dump(event, {"playlists": {str(content["playlist"].pk)}})
    assert {k: len(v) for k, v in sections.items()} == {
        "assets": 1, "fonts": 1, "themes": 2, "feeds": 1, "widgets": 1, "layouts": 1, "playlists": 1}
    assert [t["key"] for t in sections["themes"]] == ["base", "stage"]  # parents first
    assert sections["fonts"][0] == {"id": str(content["inter"].pk), "name": "Inter", "builtin": True}
    assert len(files.files) == 1 and set(mods) == {"content", "widgets", "playlists"}
    assert "auth" not in json.dumps(sections["feeds"]).replace("needs_auth", "")
    assert engine.closure(event, {"unknown": {"x"}, "layouts": set()}) == {}


def test_import_into_other_event(event, target, admin, content):
    data = _export(event, admin, {"playlists": {str(content["playlist"].pk)}}, description="All of it")
    pi = _stage(target, admin, data)
    assert pi.status == PackImport.Status.READY and pi.trust == PackImport.Trust.TRUSTED  # our own key
    assert pi.name == "Test pack" and pi.description == "All of it" and pi.contents["layouts"][0]["name"] == "Stage"
    result = services.apply(pi, actor=admin)
    assert result["warnings"] == []
    assert result["created"] == {"assets": ["Logo"], "themes": ["Base", "Stage"], "feeds": ["Info"],
                                 "widgets": ["Venues"], "layouts": ["Stage"], "playlists": ["Main loop"]}
    asset = Asset.objects.get(event=target)
    assert asset.sha256 == content["asset"].sha256 and asset.pk != content["asset"].pk
    theme = Theme.objects.get(event=target, key="stage")
    assert theme.parent == Theme.objects.get(event=target, key="base")
    assert theme.tokens["logo"] == str(asset.pk) and theme.tokens["font_heading"] == str(content["inter"].pk)
    layout = Layout.objects.get(event=target)
    assert layout.theme == theme and layout.published_id
    widget = CustomWidget.objects.get(event=target)
    props = [el["props"] for el in layout.data["elements"]]
    assert props[0]["asset"] == str(asset.pk) and props[2]["widget"] == str(widget.pk)
    assert layout.data["elements"][1]["style"]["fontFamily"] == str(content["inter"].pk)
    pl = Playlist.objects.get(event=target)
    item = pl.items.get()
    assert (pl.default_duration, item.layout, item.weight, item.tags) == (12, layout, 2, ["foyer"])
    pi.refresh_from_db()
    assert pi.status == PackImport.Status.IMPORTED and not services.staged_path(pi).exists()
    entry = AuditLog.objects.filter(action="packs.imported").get()
    assert entry.changes["created"]["layouts"] == 1 and entry.changes["trust"] == "trusted"
    assert AuditLog.objects.filter(action="packs.exported").exists()
    with pytest.raises(ValidationError, match="not ready"):
        services.apply(pi, actor=admin)

    # importing again creates copies with new keys and names
    again = services.apply(_stage(target, admin, data), actor=admin)
    assert again["created"]["playlists"] == ["Main loop (2)"]
    assert set(Layout.objects.filter(event=target).values_list("key", flat=True)) == {"stage", "stage-2"}
    assert Asset.objects.filter(event=target).count() == 1  # same file reused
    assert "assets" not in again["created"]


def test_import_warnings_and_skips(event, target, admin, content):
    content["feed"].auth_header_encrypted = "x"
    content["feed"].save()
    code = {"format": 1, "width": 1920, "height": 1080, "elements": [
        {"id": "c", "type": "code", "name": "Code", "frame": {"x": 0, "y": 0, "w": 50, "h": 50}, "style": {},
         "props": {"html": "<p>hi</p>", "css": "", "js": "", "data": []}}]}
    coded = content_services.create_layout(event, name="Coded", key="coded", actor=admin, data=code)
    data = _export(event, admin, {"widgets": {str(content["widget"].pk)}, "layouts": {str(coded.pk)}})
    nobody = User.objects.create_user(email="nobody@example.org", password="pw-nobody-1234")
    result = services.apply(_stage(target, admin, data), actor=nobody)
    assert "layouts" not in result["created"] and result["created"]["widgets"] == ["Venues"]
    text = " ".join(result["warnings"])
    assert "authorization header" in text and "Layout Coded skipped" in text


def test_import_handles_missing_parts(target, admin):
    sections = {
        "fonts": [{"id": "f1", "name": "No Such Font", "builtin": True}],
        "themes": [{"id": "t1", "key": "x", "name": "X", "tokens": {"font_body": "6a7e0000-0000-4000-8000-000000000999",
                                                                   "mode": "neon"}}],
        "feeds": [{"id": "fd", "name": "Bad", "kind": "json", "url": "ftp://example.org/"}],
        "widgets": [{"id": "w1", "name": "Orphan", "feed": "fd"}],
        "layouts": [{"id": "l1", "name": "L", "key": "l", "data": {
            "format": 1, "width": 1920, "height": 1080, "elements": [
                {"id": "t", "type": "text", "name": "T", "frame": {"x": 0, "y": 0, "w": 10, "h": 10},
                 "style": {"fontFamily": "6a7e0000-0000-4000-8000-000000000999"}, "props": {"text": "x"}}]}},
                    {"id": "l2", "name": "Broken", "key": "b", "data": {"format": 1, "elements": "nope"}}],
        "playlists": [{"id": "p1", "name": "P", "items": [{"layout": "missing"}, {"layout": "l1", "weight": "x"}]}],
    }
    out = io.BytesIO()
    packfile.write(out, name="Odd", description="", sections=sections, files=packfile.FileSet(), modules=[],
                   generator="t", signer=None)
    pi = _stage(target, admin, out.getvalue())
    assert pi.trust == PackImport.Trust.UNSIGNED
    with pytest.raises(ValidationError, match="Confirm"):
        services.apply(pi, actor=admin)
    result = services.apply(pi, actor=admin, confirmed=True)
    text = " ".join(result["warnings"])
    for part in ("No Such Font", "Theme X skipped", "Feed Bad skipped", "Widget Orphan skipped",
                 "Layout Broken skipped", "an item was skipped"):
        assert part in text, part
    layout = Layout.objects.get(event=target, key="l")
    assert layout.data["elements"][0]["style"]["fontFamily"] == "token:body"
    assert Playlist.objects.get(event=target).items.count() == 0


def test_custom_font_and_files(event, target, admin, settings):
    from pathlib import Path

    src = Path(settings.BASE_DIR, "static/fonts/atkinson-hyperlegible/atkinson-hyperlegible-latin-700-normal.woff2")
    ff = content_services.upload_font(event, SimpleUploadedFile("brand.woff2", src.read_bytes()), actor=admin,
                                      name="Brand", licence="OFL")
    data = {"format": 1, "width": 1920, "height": 1080, "elements": [
        {"id": "t", "type": "text", "name": "T", "frame": {"x": 0, "y": 0, "w": 50, "h": 20},
         "style": {"fontFamily": str(ff.family.pk)}, "props": {"text": "Hi"}}]}
    layout = content_services.create_layout(event, name="Branded", key="branded", actor=admin, data=data)
    pack = _export(event, admin, {"layouts": {str(layout.pk)}})
    result = services.apply(_stage(target, admin, pack), actor=admin)
    assert result["created"] == {"fonts": ["Brand"], "layouts": ["Branded"]}
    fam = FontFamily.objects.get(event=target, name="Brand")
    assert fam.licence == "OFL" and fam.files.count() == 1
    assert Layout.objects.get(event=target).data["elements"][0]["style"]["fontFamily"] == str(fam.pk)

    # a pack whose item points at a file that is not inside fails as a whole
    out = io.BytesIO()
    packfile.write(out, name="Broken", description="", sections={"assets": [{"id": "a", "name": "x", "file": "0" * 64}],
                   "fonts": [{"id": "f", "name": "Empty", "files": [{"file": "nope"}]}]},
                   files=packfile.FileSet(), modules=[], generator="t", signer=None)
    with pytest.raises(ValidationError, match="missing"):
        services.apply(_stage(target, admin, out.getvalue()), actor=admin, confirmed=True)
    # unknown sections (a module this server does not have) block the import
    out = io.BytesIO()
    packfile.write(out, name="Future", description="", sections={"holograms": [{"id": "h"}]},
                   files=packfile.FileSet(), modules=[], generator="t", signer=None)
    with pytest.raises(ValidationError, match="holograms"):
        services.apply(_stage(target, admin, out.getvalue()), actor=admin, confirmed=True)


def test_trust_and_policy(event, target, admin, content):
    other_key = Ed25519PrivateKey.generate()
    out = io.BytesIO()
    packfile.write(out, name="Foreign", description="", sections={"themes": [
        {"id": "t", "key": "foreign", "name": "Foreign", "tokens": {}}]}, files=packfile.FileSet(),
        modules=["content"], generator="t", signer=(other_key, "Elsewhere"))
    pi = _stage(target, admin, out.getvalue())
    assert pi.trust == PackImport.Trust.UNTRUSTED and pi.signer == "Elsewhere" and services.needs_confirmation(pi)
    settings_store.save("packs", "instance", "", {"require_trusted": True}, user=admin)
    assert "trusted key" in services.blocked_reason(pi)
    with pytest.raises(ValidationError, match="trusted key"):
        services.apply(pi, actor=admin, confirmed=True)
    row = services.trust_key(packfile.b64(other_key.public_key().public_bytes_raw()), "", actor=admin)
    assert row.name == packfile.fingerprint(row.public_key)
    pi = _stage(target, admin, out.getvalue())
    assert pi.trust == PackImport.Trust.TRUSTED and services.blocked_reason(pi) == ""
    assert services.apply(pi, actor=admin)["created"] == {"themes": ["Foreign"]}
    services.untrust_key(row, actor=admin)
    assert not TrustedKey.objects.exists()
    with pytest.raises(ValidationError, match="Ed25519"):
        services.trust_key("not-a-key", "x", actor=admin)
    assert AuditLog.objects.filter(action__in=["packs.key_trusted", "packs.key_untrusted"]).count() == 2


def test_missing_modules_and_bad_files(event, target, admin, content):
    data = _export(event, admin, {"widgets": {str(content["widget"].pk)}})
    modules.set_event(target, "widgets", False, user=admin)
    pi = _stage(target, admin, data)
    assert engine.missing_modules(target, packfile.read(data, max_bytes=10_000)) == ["widgets"]
    with pytest.raises(ValidationError, match="modules that are off"):
        services.apply(pi, actor=admin)
    bad = _stage(target, admin, b"garbage")
    assert bad.status == PackImport.Status.FAILED and "not a zip" in bad.error
    assert not services.staged_path(bad).exists()
    settings_store.save("packs", "instance", "", {"max_size_mb": 1}, user=admin)
    with pytest.raises(ValidationError, match="at most 1 MB"):
        _stage(target, admin, b"x" * (1024 * 1024 + 1))
    with pytest.raises(ValidationError, match="at least one"):
        services.export(event, {"layouts": set()}, name="x", actor=admin)
    # a staged file that disappeared
    pi2 = _stage(target, admin, _export(event, admin, {"themes": {str(content["base"].pk)}}))
    services.staged_path(pi2).unlink()
    with pytest.raises(ValidationError):
        services.apply(pi2, actor=admin)


def test_gallery_packs_import(event, admin):
    assert set(gallery.entries()) == {"welcome-board", "info-board", "wayfinding"}
    for key in gallery.entries():
        pi = services.stage_gallery(event, key, actor=admin)
        assert pi.trust == PackImport.Trust.BUILTIN and not services.needs_confirmation(pi)
        result = services.apply(pi, actor=admin)
        assert result["warnings"] == [], (key, result)
        assert result["created"].get("layouts")
    assert Playlist.objects.get(event=event, name="Welcome loop").items.count() == 2
    night = Theme.objects.get(event=event, key="festival-night")
    assert night.tokens["font_heading"] == str(FontFamily.objects.get(builtin=True, name="Inter").pk)
    board = Layout.objects.get(event=event, key="info-board")
    widget = CustomWidget.objects.get(event=event, name="On air now")
    assert board.data["elements"][2]["props"]["widget"] == str(widget.pk)
    with pytest.raises(ValidationError, match="Unknown gallery"):
        services.stage_gallery(event, "nope", actor=admin)


def test_url_import_and_cleanup(event, admin, content):
    data = _export(event, admin, {"themes": {str(content["base"].pk)}})

    class Resp:
        status_code = 200
        headers = {"Content-Type": "application/zip"}

        def iter_content(self, n):
            yield data

        def close(self):
            pass

    with mock.patch("apps.core.safefetch.socket.getaddrinfo", return_value=PUBLIC), \
            mock.patch("apps.core.safefetch.requests.get", return_value=Resp()), \
            mock.patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()):
        pi = services.stage_url(event, "https://packs.example.org/base.evacpack", actor=admin)
    pi.refresh_from_db()
    assert pi.status == PackImport.Status.READY and pi.file_name == "base.evacpack" and pi.size == len(data)
    assert services.download(pi).status == PackImport.Status.READY  # only once
    with mock.patch("apps.core.safefetch.socket.getaddrinfo", return_value=PUBLIC), \
            mock.patch("apps.core.safefetch.requests.get", side_effect=requests.ConnectionError), \
            mock.patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()):
        failed = services.stage_url(event, "https://packs.example.org/x.evacpack", actor=admin)
    failed.refresh_from_db()
    assert failed.status == PackImport.Status.FAILED
    with pytest.raises(ValidationError, match="private network"):
        services.stage_url(event, "http://127.0.0.1/x.evacpack", actor=admin)
    settings_store.save("packs", "instance", "", {"allow_url_import": False}, user=admin)
    with pytest.raises(ValidationError, match="switched off"):
        services.stage_url(event, "https://packs.example.org/x.evacpack", actor=admin)

    # cleanup: imported files go, old unreviewed imports go, stuck downloads fail
    services.apply(pi, actor=admin)
    stale = _stage(event, admin, data)
    PackImport.objects.filter(pk=stale.pk).update(created_at=timezone.now() - dt.timedelta(days=8))
    stuck = PackImport.objects.create(event=event, source="url", url="https://x.example.org/")
    PackImport.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - dt.timedelta(days=2))
    services.staged_path(stale).write_bytes(data)
    assert services.cleanup() >= 1
    assert not PackImport.objects.filter(pk=stale.pk).exists()
    assert PackImport.objects.get(pk=stuck.pk).status == PackImport.Status.FAILED
    from apps.packs.tasks import cleanup, download

    assert cleanup.run() == 0 and download.run(str(stuck.pk)) == "failed" and download.run(str(event.pk)) == "gone"


# ------------------------------------------------------------------ pages
def test_pages(client, event, admin, content):
    login_2fa(client, admin)
    base = f"/e/{event.slug}/packs/"
    r = client.get(base)
    assert r.status_code == 200 and b"Welcome board" in r.content
    assert audit_url(client, base) == []
    r = client.get(f"{base}export/")
    assert r.status_code == 200 and b"Main loop" in r.content
    assert audit_url(client, f"{base}export/") == []
    assert b"Choose at least one" in client.post(f"{base}export/", {"name": "x"}).content
    r = client.post(f"{base}export/", {"name": "Our pack!", "s_layouts": [str(content["layout"].pk)], "sign": "on"})
    assert r.status_code == 200 and r["Content-Disposition"].endswith('filename="Our-pack.evacpack"')
    data = b"".join(r.streaming_content)
    assert packfile.read(data, max_bytes=10_000_000).signed

    r = client.post(f"{base}upload/", {"file": SimpleUploadedFile("our.evacpack", data)})
    pi = PackImport.objects.get(source="upload")
    assert r.status_code == 302 and r["Location"] == f"{base}imports/{pi.pk}/"
    r = client.get(r["Location"])
    assert r.status_code == 200 and b"preview-config" in r.content and b"Signed by a trusted key" in r.content
    assert audit_url(client, f"{base}imports/{pi.pk}/") == []
    r = client.post(f"{base}imports/{pi.pk}/")
    assert r.status_code == 302 and Layout.objects.filter(event=event, key="stage-2").exists()
    r = client.get(f"{base}imports/{pi.pk}/")
    assert b"Imported" in r.content and b"Stage" in r.content
    assert audit_url(client, f"{base}imports/{pi.pk}/") == []

    assert client.post(f"{base}upload/", {}).status_code == 302
    client.post(f"{base}upload/", {"file": SimpleUploadedFile("bad.evacpack", b"nope")})
    bad = PackImport.objects.get(file_name="bad.evacpack")
    assert b"not a zip" in client.get(f"{base}imports/{bad.pk}/").content
    assert client.post(f"{base}imports/{bad.pk}/discard/").status_code == 302
    assert not PackImport.objects.filter(pk=bad.pk).exists()

    r = client.post(f"{base}gallery/wayfinding/")
    gi = PackImport.objects.get(source="gallery")
    assert r["Location"] == f"{base}imports/{gi.pk}/"
    assert b"Built in" in client.get(r["Location"]).content
    assert client.post(f"{base}gallery/nope/").status_code == 302
    assert client.post(f"{base}from-url/", {"url": "nope"}).status_code == 302
    r = client.post(f"{base}from-url/", {"url": "http://127.0.0.1/x.evacpack"}, follow=True)
    assert b"private network" in r.content
    with mock.patch("apps.packs.tasks.download.delay"), \
            mock.patch("apps.core.safefetch.socket.getaddrinfo", return_value=PUBLIC):
        r = client.post(f"{base}from-url/", {"url": "https://packs.example.org/p.evacpack"})
    fetching = PackImport.objects.get(source="url")
    r = client.get(r["Location"])
    assert b'http-equiv="refresh"' in r.content and fetching.status == PackImport.Status.FETCHING

    # unsigned pack needs the confirmation box
    out = io.BytesIO()
    packfile.write(out, name="Unsigned", description="", sections={"themes": [{"id": "t", "key": "u", "name": "U"}]},
                   files=packfile.FileSet(), modules=["content"], generator="t", signer=None)
    client.post(f"{base}upload/", {"file": SimpleUploadedFile("u.evacpack", out.getvalue())})
    ui = PackImport.objects.get(file_name="u.evacpack")
    assert b"I trust where this pack comes from" in client.get(f"{base}imports/{ui.pk}/").content
    r = client.post(f"{base}imports/{ui.pk}/", follow=True)
    assert b"Confirm that you trust" in r.content
    assert client.post(f"{base}imports/{ui.pk}/", {"confirm": "on"}).status_code == 302


def test_keys_page(client, admin):
    login_2fa(client, admin)
    r = client.get("/settings/packs/")
    own = services.own_public_key()
    assert r.status_code == 200 and own.encode() in r.content
    assert audit_url(client, "/settings/packs/") == []
    assert b"Ed25519" in client.post("/settings/packs/", {"public_key": "bad", "name": "x"}).content
    key = packfile.b64(Ed25519PrivateKey.generate().public_key().public_bytes_raw())
    assert client.post("/settings/packs/", {"public_key": key, "name": "Friends"}).status_code == 302
    row = TrustedKey.objects.get()
    assert row.name == "Friends" and b"Friends" in client.get("/settings/packs/").content
    assert client.post(f"/settings/packs/{row.pk}/remove/").status_code == 302
    assert not TrustedKey.objects.exists()


def test_permissions_and_module_switch(client, event, admin, member, orga, content):
    base = f"/e/{event.slug}/packs/"
    login_2fa(client, member)  # viewer: no pack permissions
    assert client.get(base).status_code == 403
    assert client.get(f"{base}export/").status_code == 403
    assert client.post(f"{base}gallery/wayfinding/").status_code == 403
    assert client.get("/settings/packs/").status_code in (302, 403)
    login_2fa(client, orga)
    assert client.get(base).status_code == 200
    modules.set_event(event, "packs", False, user=admin)
    assert client.get(base).status_code == 404


def test_cli(event, target, admin, content, tmp_path):
    out = io.StringIO()
    call_command("evac_pack", "key", stdout=out)
    assert services.own_public_key() in out.getvalue()
    path = tmp_path / "p.evacpack"
    call_command("evac_pack", "export", event.slug, str(path), f"--playlists={content['playlist'].pk}",
                 stdout=io.StringIO())
    out = io.StringIO()
    call_command("evac_pack", "verify", str(path), stdout=out)
    assert "valid, trusted" in out.getvalue() and "playlists: 1" in out.getvalue()
    out = io.StringIO()
    call_command("evac_pack", "import", target.slug, str(path), stdout=out)
    assert "playlists: Main loop" in out.getvalue()
    unsigned = tmp_path / "u.evacpack"
    call_command("evac_pack", "export", event.slug, str(unsigned), f"--themes={content['base'].pk}", "--unsigned",
                 stdout=io.StringIO())
    with pytest.raises(CommandError, match="Confirm"):
        call_command("evac_pack", "import", target.slug, str(unsigned), stdout=io.StringIO())
    call_command("evac_pack", "import", target.slug, str(unsigned), "--yes", stdout=io.StringIO())
    with pytest.raises(CommandError, match="Unknown event"):
        call_command("evac_pack", "import", "nope", str(path))
    with pytest.raises(CommandError, match="at least one"):
        call_command("evac_pack", "export", event.slug, str(tmp_path / "e.evacpack"))
    assert not (tmp_path / "e.evacpack").exists()
    (tmp_path / "bad.evacpack").write_bytes(b"x")
    with pytest.raises(CommandError, match="not a zip"):
        call_command("evac_pack", "verify", str(tmp_path / "bad.evacpack"))
    with pytest.raises(CommandError, match="not a zip"):
        call_command("evac_pack", "import", target.slug, str(tmp_path / "bad.evacpack"))
