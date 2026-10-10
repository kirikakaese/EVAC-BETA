# SPDX-License-Identifier: AGPL-3.0-or-later
"""pretalx, frab/Pentabarf and iCal imports (roadmap 5.2, ADR-0038)."""
import datetime as dt
import json
from pathlib import Path
from unittest import mock

import pytest

from apps.core import modules, outbox, safefetch
from apps.core.models import OutboxJob
from apps.core.registry import registry
from apps.extensions import services as ext
from apps.extensions.models import ExtensionLog
from apps.schedule import services as program
from apps.schedule.models import Session
from conftest import login_2fa
from extensions.program_import import importer, parse, tasks

XML = (Path(__file__).parent / "fixtures" / "schedule.xml").read_bytes()
UTC = dt.UTC

JSON = json.dumps({"schedule": {"version": "1", "conference": {
    "acronym": "camp", "title": "Demo Camp", "time_zone_name": "Europe/Berlin", "days": [
        {"index": 1, "date": "2026-07-01", "rooms": {
            "Hall A": [{"guid": "g1", "id": 1, "date": "2026-07-01T10:00:00+02:00", "start": "10:00",
                        "duration": "00:30", "room": "Hall A", "title": "Opening", "track": "Main",
                        "persons": [{"code": "ABC", "public_name": "Ada"}]}],
            "Hall B": [{"id": 2, "start": "12:00", "duration": "1:00:00", "title": "Workshop", "persons": []}]}}]}}}
                  ).encode()

ICS = (b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:a@x\r\nDTSTART:20260701T080000Z\r\n"
       b"DTEND:20260701T090000Z\r\nSUMMARY:Opening\\, with coffee\r\nLOCATION:Hall A\r\nCATEGORIES:Main,Other\r\n"
       b"DESCRIPTION:Line one\\nline two that is long enough to be folded by a well-behaved calendar exp\r\n"
       b" orter\r\nEND:VEVENT\r\n"
       b"BEGIN:VEVENT\r\nUID:b@x\r\nDTSTART;TZID=Europe/Berlin:20260701T120000\r\nDURATION:PT1H30M\r\n"
       b"SUMMARY:Workshop\r\nSTATUS:CANCELLED\r\nEND:VEVENT\r\n"
       b"BEGIN:VEVENT\r\nUID:c@x\r\nDTSTART;VALUE=DATE:20260701\r\nSUMMARY:All day\r\nEND:VEVENT\r\n"
       b"BEGIN:VEVENT\r\nUID:d@x\r\nDTSTART:20260701T1400\r\nRRULE:FREQ=DAILY\r\nSUMMARY:Daily\r\nEND:VEVENT\r\n"
       b"BEGIN:VEVENT\r\nUID:d@x\r\nRECURRENCE-ID:20260702T140000\r\nDTSTART:20260702T150000\r\n"
       b"SUMMARY:Daily (moved)\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


# ------------------------------------------------------------------ parsers
def test_frab_xml():
    items = parse.frab_xml(XML, "UTC")
    assert [i.title for i in items] == ["Opening", "CANCELLED: Soldering", "Late night"]
    o = items[0]
    assert o.starts_at == dt.datetime(2026, 7, 1, 8, 0, tzinfo=UTC) and o.ends_at - o.starts_at == dt.timedelta(
        minutes=45)
    assert (o.stage, o.track, o.kind, o.language, o.subtitle) == ("Hall A", "Main", "lecture", "en",
                                                                  "Welcome to camp")
    assert o.speakers == [("p-7", "Ada Lovelace")]
    s = items[1]
    assert s.external_id == "102" and s.cancelled and s.stage == "Hall A"
    assert s.starts_at == dt.datetime(2026, 7, 1, 9, 0, tzinfo=UTC)  # day + start in the conference time zone
    with pytest.raises(parse.ParseError, match="not XML"):
        parse.frab_xml(b"<oops", "UTC")
    with pytest.raises(parse.ParseError, match="frab"):
        parse.frab_xml(b"<calendar/>", "UTC")
    with pytest.raises(parse.ParseError, match="duration"):
        parse.frab_xml(XML.replace(b"<duration>00:45</duration>", b"<duration>long</duration>"), "UTC")


def test_frab_json():
    items = parse.frab_json(JSON, "UTC")
    assert [(i.external_id, i.stage) for i in items] == [("g1", "Hall A"), ("2", "Hall B")]
    assert items[0].speakers == [("ABC", "Ada")]
    assert items[1].ends_at - items[1].starts_at == dt.timedelta(hours=1)
    assert items[1].starts_at == dt.datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    for bad in (b"nope", b"{}", b'{"schedule": {"conference": {}}}'):
        with pytest.raises(parse.ParseError):
            parse.frab_json(bad, "UTC")


def test_ical():
    items = parse.ical(ICS, "Europe/Berlin")
    by = {i.external_id: i for i in items}
    assert set(by) == {"a@x", "b@x", "d@x#20260702T140000"}  # no all-day event, no recurring master
    a = by["a@x"]
    assert a.title == "Opening, with coffee" and a.stage == "Hall A" and a.track == "Main"
    assert a.abstract.endswith("calendar exporter") and "\n" in a.abstract
    b = by["b@x"]
    assert b.cancelled and b.starts_at == dt.datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    assert b.ends_at - b.starts_at == dt.timedelta(minutes=90)
    assert by["d@x#20260702T140000"].starts_at == dt.datetime(2026, 7, 2, 13, 0, tzinfo=UTC)  # floating: Berlin
    with pytest.raises(parse.ParseError, match="iCalendar"):
        parse.ical(b"hello", "UTC")
    with pytest.raises(parse.ParseError, match="DURATION"):
        parse.ical(b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:x\nDURATION:soon\nEND:VEVENT\nEND:VCALENDAR", "UTC")
    assert parse._zone("Not/AZone") is UTC


# ------------------------------------------------------------------ the extensions
def configure(event, key, values, secrets=None):
    spec = registry.get_extension(key)
    cfg = ext.get_or_new(spec, event)
    return ext.save_config(cfg, settings_values=values, secret_values=secrets or {},
                           features={f.key: True for f in spec.features}, enabled=True)


def fetched(body):
    return safefetch.Fetched(200, body, "application/xml", "")


def test_urls_and_tokens(event):
    p = configure(event, "pretalx", {"base_url": "https://pretalx.example.org/", "event": "camp"},
                  {"token": "secret-token"})
    assert importer.url_of(p) == "https://pretalx.example.org/camp/schedule/export/schedule.json"
    with mock.patch.object(safefetch, "get", return_value=fetched(JSON)) as get:
        items = importer.fetch(p)
    assert len(items) == 2 and get.call_args.kwargs["headers"] == {"Authorization": "Token secret-token"}
    assert get.call_args.kwargs["allow_private"] is False
    f = configure(event, "frab", {"url": "https://example.org/schedule.xml"})
    with mock.patch.object(safefetch, "get", return_value=fetched(XML)) as get:
        assert len(importer.fetch(f)) == 3
    assert get.call_args.kwargs["headers"] == {}
    i = configure(event, "ical", {"url": "https://example.org/camp.ics"})
    with mock.patch.object(safefetch, "get", return_value=fetched(ICS)):
        assert len(importer.fetch(i)) == 3
    i.settings = {}
    with pytest.raises(safefetch.FetchError):
        importer.fetch(i)


def test_test_connection_and_sync_job(event, admin, django_capture_on_commit_callbacks):
    cfg = configure(event, "frab", {"url": "https://example.org/schedule.xml", "interval_minutes": 5})
    with mock.patch.object(safefetch, "get", return_value=fetched(XML)):
        result = importer.test_connection(cfg)
        assert result.ok and "3 sessions on 2 stages" in result.message and not Session.objects.exists()
        job = importer.queue(cfg)
        assert importer.queue(cfg).pk == job.pk  # one per 30 s
        with django_capture_on_commit_callbacks(execute=True):
            assert outbox.deliver(job)
    assert Session.objects.filter(event=event, source=importer.source_of(cfg)).count() == 3
    cfg.refresh_from_db()
    assert cfg.last_sync_at and cfg.last_error == ""
    assert ExtensionLog.objects.filter(config=cfg, message__startswith="Program sync: 3 new").exists()

    # a broken source: logged, nothing deleted
    with mock.patch.object(safefetch, "get", return_value=fetched(b"<broken")):
        job = OutboxJob(payload={"config": str(cfg.pk)})
        importer.handle_job(job)
        assert "failed" in job.result and not importer.test_connection(cfg).ok
    cfg.refresh_from_db()
    assert "not XML" in cfg.last_error and Session.objects.count() == 3

    modules.set_event(event, "program", False)
    job = OutboxJob(payload={"config": str(cfg.pk)})
    importer.handle_job(job)
    assert job.result == {"skipped": "program module off"}
    modules.set_event(event, "program", True)
    cfg.features = {"sync": False}
    cfg.save()
    job = OutboxJob(payload={"config": str(cfg.pk)})
    importer.handle_job(job)
    assert job.result == {"skipped": "gone or disabled"}
    assert importer.sync_due(dt.datetime.now(UTC) + dt.timedelta(days=1)) == 0
    job = OutboxJob(payload={"config": "00000000-0000-0000-0000-000000000000"})
    importer.handle_job(job)
    assert job.result == {"skipped": "gone or disabled"}

    # purge removes what this source created, nothing else
    program.merge(event, "frab:other", [program.Imported("x", "Other", dt.datetime(2026, 7, 1, tzinfo=UTC),
                                                         dt.datetime(2026, 7, 1, 1, tzinfo=UTC))])
    importer.purge(cfg)
    assert list(Session.objects.values_list("title", flat=True)) == ["Other"]


def test_sync_due(event):
    cfg = configure(event, "ical", {"url": "https://example.org/camp.ics", "interval_minutes": 10})
    off = configure(event, "frab", {"url": "https://example.org/s.xml", "interval_minutes": 0})
    with mock.patch.object(importer, "queue") as queue:
        assert tasks.sync_due() == 1
        assert queue.call_args.args[0] == cfg
        cfg.last_sync_at = dt.datetime.now(UTC)
        cfg.save()
        assert tasks.sync_due() == 0
        assert importer.sync_due(dt.datetime.now(UTC) + dt.timedelta(minutes=11)) == 1
    assert off.pk


def test_sync_now_view_and_sources(client, admin, event):
    cfg = configure(event, "frab", {"url": "https://example.org/schedule.xml"})
    login_2fa(client, admin)
    page = client.get(f"/e/{event.slug}/schedule/")
    assert b"frab / Pentabarf" in page.content and b"x/sync/" in page.content
    with mock.patch.object(importer, "queue") as queue:
        r = client.post(f"/e/{event.slug}/settings/extensions/frab/x/sync/")
    assert r.status_code == 302 and queue.call_args.args[0] == cfg
    assert client.get(f"/e/{event.slug}/settings/extensions/frab/x/").status_code == 302
