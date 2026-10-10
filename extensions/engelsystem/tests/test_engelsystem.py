# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engelsystem import (roadmap 7.1, ADR-0041) against a fake API v0-beta."""
import datetime as dt
import json
from unittest import mock

import pytest

from apps.core import modules, safefetch
from apps.core.registry import registry
from apps.crew import services as crew
from apps.crew.models import Assignment, Member, Shift, Team
from apps.extensions import services as ext
from apps.extensions.models import ExtensionLog
from conftest import login_2fa
from extensions.engelsystem import importer, tasks

pytestmark = pytest.mark.django_db
START = dt.datetime(2030, 7, 1, 10, tzinfo=dt.UTC)


def configure(event, values=None, secrets=None):
    spec = registry.get_extension("engelsystem")
    cfg = ext.get_or_new(spec, event)
    return ext.save_config(cfg, settings_values={"base_url": "https://engel.example.org", **(values or {})},
                           secret_values=secrets or {"api_key": "k3y"},
                           features={f.key: True for f in spec.features}, enabled=True)


def shift_doc(sid, type_id, entries, needs=2, start=START, name="Bar shift", location="Hall A"):
    return {"id": sid, "name": name, "description": "Pour drinks", "starts_at": start.isoformat(),
            "ends_at": (start + dt.timedelta(hours=3)).isoformat(), "location": {"id": 1, "name": location},
            "shift_type": {"id": 1, "name": "Bar"},
            "needed_angel_types": [{"angel_type": {"id": type_id, "name": "x"}, "needs": needs,
                                    "entries": [{"id": u, "user": {"id": u, "name": f"Angel {u}"}}
                                                for u in entries]}]}


class Fake:
    def __init__(self):
        self.types = [{"id": 5, "name": "Bar angel"}, {"id": 6, "name": "Build angel"}]
        self.shifts = {5: [shift_doc(100, 5, [1, 2])], 6: [shift_doc(200, 6, [3], name="Stage build")]}
        self.calls = []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        path = url.split("/api/v0-beta", 1)[1]
        if path == "/angeltypes":
            body = {"data": self.types}
        elif path == "/info":
            body = {"name": "Camp Engelsystem"}
        else:
            body = {"data": self.shifts[int(path.split("/")[2])]}
        return safefetch.Fetched(200, json.dumps(body).encode(), "application/json", "")


def test_sync_creates_and_merges(event, venue):
    cfg = configure(event)
    fake = Fake()
    with mock.patch.object(safefetch, "get", fake):
        stats = importer.run(cfg)
    assert fake.calls[0][0] == "https://engel.example.org/api/v0-beta/angeltypes"
    assert fake.calls[0][1]["headers"] == {"Authorization": "Bearer k3y"}
    assert stats["teams"] == 2 and stats["shifts_new"] == 2 and stats["signups"] == 3
    bar = Shift.objects.get(external_id="100:5")
    assert bar.team.name == "Bar angel" and bar.needed == 2 and bar.location == "Hall A"
    assert bar.room is not None and bar.room.name == "Hall A"
    assert ExtensionLog.objects.filter(config=cfg, message__contains="2 new").exists()
    # local activity: angel 1 checks in, a local person signs up; angel 2 leaves upstream; shift 200 disappears
    a1 = Assignment.objects.get(shift=bar, member__external_id="1")
    crew.check_in(a1, actor=None)
    local = crew.save_member(Member(event=event, name="Local"), actor=None)
    crew.sign_up(bar, local, actor=None, force=True)
    fake.shifts[5] = [shift_doc(100, 5, [1], needs=3, name="Bar shift (late)")]
    fake.shifts[6] = []
    with mock.patch.object(safefetch, "get", fake):
        stats = importer.run(cfg)
    bar.refresh_from_db()
    assert bar.title == "Bar shift (late)" and bar.needed == 3 and stats["shifts_updated"] == 1
    people = set(bar.assignments.values_list("member__name", "status"))
    assert people == {("Angel 1", "checked_in"), ("Local", "signed_up")}
    assert stats["shifts_removed"] == 1 and not Shift.objects.filter(external_id="200:6").exists()
    # a vanished shift with a check-in stays
    fake.shifts[5] = []
    with mock.patch.object(safefetch, "get", fake):
        stats = importer.run(cfg)
    assert stats["kept"] == 1 and Shift.objects.filter(external_id="100:5").exists()


def test_filter_adopt_and_purge(event):
    Team.objects.create(event=event, name="Bar angel")  # made by hand: adopted, not duplicated
    cfg = configure(event, {"angeltypes": ["bar angel"]})
    with mock.patch.object(safefetch, "get", Fake()):
        importer.run(cfg)
    assert list(Team.objects.values_list("name", "source")) == [("Bar angel", importer.source_of(cfg))]
    assert Shift.objects.count() == 1
    importer.purge(cfg)
    assert not Shift.objects.exists() and not Member.objects.exists()


def test_errors_and_connection(event):
    cfg = configure(event)
    bad = safefetch.Fetched(200, b"<html>", "text/html", "")
    with mock.patch.object(safefetch, "get", return_value=bad):
        assert not importer.test_connection(cfg).ok
    with mock.patch.object(safefetch, "get", side_effect=safefetch.FetchError("refused")):
        with pytest.raises(importer.SyncError, match="refused"):
            importer.run(cfg)
    with mock.patch.object(safefetch, "get", Fake()):
        res = importer.test_connection(cfg)
    assert res.ok and "Camp Engelsystem" in res.message and "2 angel types" in res.message
    cfg.settings = {}
    with pytest.raises(importer.SyncError, match="URL"):
        importer._base(cfg)


def test_job_and_sync_due(event):
    cfg = configure(event, {"interval_minutes": 10})
    with mock.patch.object(importer, "queue") as queue:
        assert tasks.sync_due() == 1
    assert queue.call_args.args[0] == cfg
    job = mock.Mock(payload={"config": str(cfg.pk)})
    with mock.patch.object(safefetch, "get", side_effect=safefetch.FetchError("down")):
        importer.handle_job(job)
    assert job.result == {"failed": "down"}
    cfg.refresh_from_db()
    assert cfg.last_error == "down"
    with mock.patch.object(safefetch, "get", Fake()):
        importer.handle_job(job)
    assert job.result["shifts_new"] == 2
    modules.set_instance("crew", False)
    importer.handle_job(job)
    assert job.result == {"skipped": "crew module off"}
    job2 = importer.queue(cfg)
    assert job2.kind == importer.JOB


def test_sync_now_from_shift_board(client, admin, event):
    cfg = configure(event)
    login_2fa(client, admin)
    page = client.get(f"/e/{event.slug}/crew/")
    assert b"Engelsystem" in page.content and b"x/sync/" in page.content
    assert b"Engelsystem" not in client.get(f"/e/{event.slug}/schedule/").content
    with mock.patch.object(importer, "queue") as queue:
        r = client.post(f"/e/{event.slug}/settings/extensions/engelsystem/x/sync/")
    assert r.status_code == 302 and queue.call_args.args[0] == cfg
    assert client.get(f"/e/{event.slug}/settings/extensions/engelsystem/x/").status_code == 302
