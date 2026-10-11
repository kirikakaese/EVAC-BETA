# SPDX-License-Identifier: AGPL-3.0-or-later
"""pretix import and check-in sync (roadmap 8.2, ADR-0044) against a fake pretix API."""
import datetime as dt
import json
from unittest import mock

import pytest

from apps.access import services as access
from apps.access.models import AccessZone, Attendee, TicketType
from apps.core import modules, safefetch
from apps.core.models import OutboxJob
from apps.core.registry import registry
from apps.extensions import services as ext
from apps.extensions.models import ExtensionLog
from conftest import login_2fa
from extensions.pretix import importer, tasks

pytestmark = pytest.mark.django_db
API = "https://pretix.example.org/api/v1/organizers/camp/events/camp26"


def configure(event, values=None, secrets=None):
    spec = registry.get_extension("pretix")
    cfg = ext.get_or_new(spec, event)
    return ext.save_config(cfg, settings_values={"base_url": "https://pretix.example.org", "organizer": "camp",
                                                 "event": "camp26", **(values or {})},
                           secret_values=secrets or {"api_token": "t0k"},
                           features={f.key: True for f in spec.features}, enabled=True)


def position(pid, item, secret, name, checkins=(), canceled=False):
    return {"id": pid * 10, "positionid": pid, "item": item, "secret": secret, "attendee_name": name,
            "attendee_email": None, "company": "", "canceled": canceled,
            "checkins": [{"list": 1, "datetime": c, "type": "entry"} for c in checkins]}


class Fake:
    def __init__(self):
        self.items = [{"id": 1, "name": {"en": "Day ticket"}, "admission": True},
                      {"id": 2, "name": {"en": "T-shirt"}, "admission": False},
                      {"id": 3, "name": {"en": "Weekend"}, "admission": True}]
        self.orders = [
            {"code": "ABC12", "status": "p", "email": "ada@example.org", "positions": [
                position(1, 1, "secretada", "Ada Lovelace"), position(2, 2, "shirt", None)]},
            {"code": "DEF34", "status": "p", "email": "bob@example.org", "positions": [
                position(1, 3, "secretbob", None, checkins=["2030-07-01T10:00:00Z"])]},
            {"code": "GHI56", "status": "n", "email": "carl@example.org", "positions": [
                position(1, 1, "secretcarl", "Carl")]},
            {"code": "JKL78", "status": "c", "email": "dora@example.org", "positions": [
                position(1, 1, "secretdora", "Dora")]},
        ]
        self.calls = []

    def page(self, rows, path, size=2):
        start = 0
        if "page=" in path:
            start = int(path.split("page=")[1]) * size
        nxt = f"{API}/orders/?testmode=false&page={start // size + 1}" if start + size < len(rows) else None
        return {"count": len(rows), "next": nxt, "results": rows[start:start + size]}

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        path = url.split("/events/camp26", 1)[1]
        if path == "/":
            body = {"name": {"en": "Camp 2026"}, "slug": "camp26"}
        elif path.startswith("/items/"):
            body = {"count": 3, "next": None, "results": self.items}
        elif path.startswith("/checkinlists/"):
            body = {"count": 1, "next": None, "results": [{"id": 7, "name": "Entrance"}]}
        else:
            body = self.page(self.orders, path)
        return safefetch.Fetched(200, json.dumps(body).encode(), "application/json", "")


def test_sync(event):
    cfg = configure(event)
    fake = Fake()
    with mock.patch.object(safefetch, "get", fake):
        stats = importer.run(cfg)
    assert fake.calls[0][1]["headers"]["Authorization"] == "Token t0k"
    assert stats == {"types": 2, "added": 4, "updated": 0, "cancelled": 0, "checked_in": 1, "skipped": 1}
    assert sorted(TicketType.objects.values_list("name", flat=True)) == ["Day ticket", "Weekend"]
    ada = Attendee.objects.get(code="secretada")
    assert ada.name == "Ada Lovelace" and ada.status == "valid" and ada.external_id == "ABC12-1"
    bob = Attendee.objects.get(code="secretbob")
    assert bob.name == "bob@example.org" and bob.checked_in_at == dt.datetime(2030, 7, 1, 10, tzinfo=dt.UTC)
    assert Attendee.objects.get(code="secretcarl").status == "cancelled"  # pending is not valid by default
    assert Attendee.objects.get(code="secretdora").status == "cancelled"
    assert not Attendee.objects.filter(code="shirt").exists()
    assert ExtensionLog.objects.filter(config=cfg, message__contains="4 new").exists()
    # pending counts as valid when configured; a removed position is cancelled; local zone grants stay
    zone = AccessZone.objects.create(event=event, name="Backstage")
    TicketType.objects.get(name="Weekend").zones.add(zone)
    cfg.settings = {**cfg.settings, "pending_valid": True}
    cfg.save()
    fake.orders = fake.orders[1:3]
    fake.orders[0]["positions"][0]["attendee_name"] = "Bob Builder"
    with mock.patch.object(safefetch, "get", fake):
        stats = importer.run(cfg)
    assert stats["cancelled"] == 1 and stats["updated"] == 2
    assert Attendee.objects.get(code="secretada").status == "cancelled"
    assert Attendee.objects.get(code="secretcarl").status == "valid"
    assert Attendee.objects.get(code="secretbob").name == "Bob Builder"
    assert list(TicketType.objects.get(name="Weekend").zones.all()) == [zone]
    # the pretix ticket's QR code works at EVAC's scanners
    assert access.scan(zone, "secretbob")[0].result == "ok"


def test_adopt_manual_type_and_purge(event):
    TicketType.objects.create(event=event, name="Day ticket")
    cfg = configure(event)
    with mock.patch.object(safefetch, "get", Fake()):
        importer.run(cfg)
    assert TicketType.objects.filter(name="Day ticket").count() == 1
    importer.purge(cfg)
    assert not Attendee.objects.exists() and not TicketType.objects.exists()


def test_errors_and_connection(event):
    cfg = configure(event)
    with mock.patch.object(safefetch, "get", return_value=safefetch.Fetched(200, b"<html>", "text/html", "")):
        assert not importer.test_connection(cfg).ok
    with mock.patch.object(safefetch, "get", return_value=safefetch.Fetched(200, b'{"x": 1}', "", "")):
        with pytest.raises(importer.SyncError, match="Unexpected"):
            importer.fetch(cfg)
    with mock.patch.object(safefetch, "get", side_effect=safefetch.FetchError("refused")):
        with pytest.raises(importer.SyncError, match="refused"):
            importer.run(cfg)
    with mock.patch.object(safefetch, "get", Fake()):
        res = importer.test_connection(cfg)
    assert res.ok and "Camp 2026" in res.message and "2 admission products" in res.message and "7: Entrance" in \
        res.message
    evil = Fake()
    evil.page = lambda rows, path, size=2: {"count": 9, "next": "https://evil.example.com/x", "results": []}
    with mock.patch.object(safefetch, "get", evil):
        with pytest.raises(importer.SyncError, match="another server"):
            importer.fetch(cfg)
    cfg.settings = {"base_url": "https://x"}
    with pytest.raises(importer.SyncError, match="organizer"):
        importer._base(cfg)
    assert importer.text({"de": "Tagesticket"}) == "Tagesticket" and importer.text(None) == ""


def test_checkins_go_back_to_pretix(event, admin, django_capture_on_commit_callbacks):
    cfg = configure(event, {"checkin_list": 7})
    with mock.patch.object(safefetch, "get", Fake()):
        importer.run(cfg)
    zone = AccessZone.objects.create(event=event, name="Entrance", open_to_all=True, checkin=True)
    with django_capture_on_commit_callbacks(execute=True):
        assert access.scan(zone, "secretada", actor=admin)[0].result == "ok"
    job = OutboxJob.objects.get(kind=importer.CHECKIN_JOB)
    resp = mock.Mock(status_code=201)
    resp.json.return_value = {"status": "ok"}
    with mock.patch.object(safefetch, "check_url", side_effect=safefetch.FetchError("Unknown host")):
        importer.handle_checkin(job)
    assert job.result == {"failed": "Unknown host"}
    with mock.patch("requests.post", return_value=resp) as post, mock.patch.object(safefetch, "check_url"):
        importer.handle_checkin(job)
    url, kw = post.call_args[0][0], post.call_args[1]
    assert url == "https://pretix.example.org/api/v1/organizers/camp/checkinrpc/redeem/"
    assert kw["json"]["secret"] == "secretada" and kw["json"]["lists"] == [7] and kw["allow_redirects"] is False
    assert job.result == {"status": 201, "pretix": "ok"}
    resp.status_code = 503
    with mock.patch("requests.post", return_value=resp), mock.patch.object(safefetch, "check_url"), \
            pytest.raises(RuntimeError):
        importer.handle_checkin(job)
    # check-ins that came from pretix are not sent back; manual attendees neither
    importer.on_event("access.checked_in", {"source": "", "id": "x"}, event)
    importer.on_event("access.refused", {"source": importer.source_of(cfg)}, event)
    assert OutboxJob.objects.filter(kind=importer.CHECKIN_JOB).count() == 1


def test_job_sync_due_and_views(client, admin, event):
    cfg = configure(event, {"interval_minutes": 5})
    with mock.patch.object(importer, "queue") as queue:
        assert tasks.sync_due() == 1
    assert queue.call_args.args[0] == cfg
    job = mock.Mock(payload={"config": str(cfg.pk)})
    with mock.patch.object(safefetch, "get", side_effect=safefetch.FetchError("down")):
        importer.handle_job(job)
    assert job.result == {"failed": "down"}
    with mock.patch.object(safefetch, "get", Fake()):
        importer.handle_job(job)
    assert job.result["added"] == 4
    modules.set_instance("access", False)
    importer.handle_job(job)
    assert job.result == {"skipped": "access module off"}
    modules.set_instance("access", True)
    c = login_2fa(client, admin)
    page = c.get(f"/e/{event.slug}/access/")
    assert b"pretix" in page.content and b"x/sync/" in page.content
    with mock.patch.object(importer, "queue") as queue:
        r = c.post(f"/e/{event.slug}/settings/extensions/pretix/x/sync/")
    assert r.status_code == 302 and queue.call_args.args[0] == cfg
    assert importer.queue(cfg).kind == importer.JOB
