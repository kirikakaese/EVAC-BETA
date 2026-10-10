# SPDX-License-Identifier: AGPL-3.0-or-later
"""Program module (roadmap 5.1, ADR-0038): live changes, imports with local overrides, screens, public page,
exports, API, anchors and the module switch."""
import datetime as dt
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken
from apps.core import modules, settings_store
from apps.core.a11y import audit_url
from apps.core.models import AuditLog
from apps.schedule import exports, services
from apps.schedule.models import Session, SessionChange, Stage
from conftest import login_2fa

from .conftest import at, imported


# ------------------------------------------------------------------ live changes
def test_delay_cancel_move_restore(event, stages, talk, later, admin, django_capture_on_commit_callbacks):
    with mock.patch.object(services, "push_screens") as push, \
            django_capture_on_commit_callbacks(execute=True):
        services.delay(talk, 10, actor=admin, shift_following=True)
    assert push.called
    talk.refresh_from_db()
    later.refresh_from_db()
    assert talk.delay_minutes == 10 and talk.note == "Starts 10 min late" and talk.changed
    assert later.delay_minutes == 10  # the following session on the stage moved too, also across midnight
    assert SessionChange.objects.filter(session=talk, kind="delay").exists()
    assert AuditLog.objects.filter(action="program.delay").count() == 2
    services.delay(talk, -10, actor=admin)
    talk.refresh_from_db()
    assert talk.delay_minutes == 0 and SessionChange.objects.filter(session=talk, kind="restore").exists()
    services.delay(talk, -5, actor=admin)
    assert SessionChange.objects.filter(session=talk, kind="earlier").exists()
    with pytest.raises(ValidationError):
        services.delay(talk, 0, actor=admin)

    services.move(talk, stages["ws"], actor=admin)
    talk.refresh_from_db()
    assert talk.moved and talk.note == "Moved to Workshop"
    with pytest.raises(ValidationError, match="already there"):
        services.move(talk, stages["ws"], actor=admin)
    services.cancel(talk, actor=admin, note="Speaker ill")
    with pytest.raises(ValidationError, match="Already"):
        services.cancel(talk, actor=admin)
    services.restore(talk, actor=admin)
    talk.refresh_from_db()
    assert (talk.status, talk.stage, talk.delay_minutes, talk.note) == ("scheduled", stages["main"], 0, "")
    with pytest.raises(ValidationError, match="Nothing"):
        services.restore(talk, actor=admin)
    services.reschedule(talk, at(120), at(150), actor=admin)
    talk.refresh_from_db()
    assert talk.delay_minutes == 135 and "New time" in talk.note


def test_shift_following_crosses_midnight_within_horizon(event, stages, admin):
    night = dt.datetime(2030, 7, 1, 23, 30, tzinfo=dt.UTC)
    first = services.save_session(Session(event=event, title="Late set", stage=stages["main"], starts_at=night,
                                          ends_at=night + dt.timedelta(minutes=45)), actor=admin)
    after = services.save_session(Session(event=event, title="After midnight", stage=stages["main"],
                                          starts_at=night + dt.timedelta(hours=1),
                                          ends_at=night + dt.timedelta(hours=2)), actor=admin)
    far = services.save_session(Session(event=event, title="Next evening", stage=stages["main"],
                                        starts_at=night + dt.timedelta(hours=services.FOLLOWING_HOURS + 1),
                                        ends_at=night + dt.timedelta(hours=services.FOLLOWING_HOURS + 2)),
                                actor=admin)
    with mock.patch.object(services, "push_screens"):
        services.delay(first, 15, actor=admin, shift_following=True)
    after.refresh_from_db()
    far.refresh_from_db()
    assert after.delay_minutes == 15 and far.delay_minutes == 0


def test_validation(event, stages, admin):
    from apps.events import services as ev

    other = ev.create_event(name="Other", slug="other", user=admin, timezone="UTC",
                            start_date=dt.date(2026, 7, 1), end_date=dt.date(2026, 7, 2))
    foreign = Stage.objects.create(event=other, name="Elsewhere")
    for s, msg in ((Session(event=event, title=" ", starts_at=at(0), ends_at=at(10)), "title"),
                   (Session(event=event, title="X", starts_at=at(10), ends_at=at(0)), "end"),
                   (Session(event=event, title="X", starts_at=at(0), ends_at=at(10), stage=foreign), "another")):
        with pytest.raises(ValidationError, match=msg):
            services.save_session(s, actor=admin)


def test_live_changes_wait_while_checked_out(event, talk, admin):
    from apps.nodes import guard

    with mock.patch.object(guard, "ensure_local", side_effect=guard.CheckedOut("checked out to the node")), \
            pytest.raises(ValidationError, match="node"):
        services.delay(talk, 5, actor=admin)


# ------------------------------------------------------------------ import
def test_merge_keeps_local_changes(event, admin, venue):
    src = "frab:1"
    items = [imported("a", "Opening", at(0), at(30), stage="Hall A", track="Main", speakers=[("p1", "Ada")]),
             imported("b", "Workshop", at(60), at(120), stage="Lab"),
             imported("c", "Closing", at(200), at(230), stage="Hall A")]
    r = services.merge(event, src, items, actor=admin)
    assert (r.created, r.updated) == (3, 0)
    a = Session.objects.get(external_id="a")
    assert a.stage.room.name == "Hall A"  # matched to the venue's room by name
    assert [p.name for p in a.speakers.all()] == ["Ada"]
    assert services.merge(event, src, items).unchanged == 3

    # local: a delayed, b cancelled, c's title edited in the form
    services.delay(a, 15, actor=admin)
    b = Session.objects.get(external_id="b")
    services.cancel(b, actor=admin)
    c = Session.objects.get(external_id="c")
    c.title = "Closing ceremony"
    services.save_session(c, actor=admin, changed=["title"])
    assert c.overrides == ["title"]

    # the source moves a and renames c and b; then drops c
    items2 = [imported("a", "Opening!", at(5), at(35), stage="Hall A", track="Main", speakers=[("p1", "Ada")]),
              imported("b", "Workshop II", at(60), at(120), stage="Lab"),
              imported("c", "Closing 2", at(200), at(230), stage="Hall A"),
              imported("d", "New", at(300), at(330), cancelled=True)]
    r = services.merge(event, src, items2)
    a.refresh_from_db(), b.refresh_from_db(), c.refresh_from_db()
    assert a.title == "Opening!" and a.starts_at == at(15) and a.delay_minutes == 15  # local delay kept
    assert b.title == "Workshop II" and b.status == "cancelled"  # local cancellation kept
    assert c.title == "Closing ceremony"
    assert Session.objects.get(external_id="d").status == "cancelled"
    assert r.created == 1 and r.kept_local >= 2
    r = services.merge(event, src, items2[:2])
    c.refresh_from_db()
    assert c.missing_upstream and r.missing == 1 and r.removed == 1  # c changed here stays, d is deleted
    assert not Session.objects.filter(external_id="d").exists()
    assert "gone from the source" in r.summary()

    # reset: back to the source on the next sync
    services.reset_overrides(c, actor=admin)
    services.restore(b, actor=admin)
    services.merge(event, src, items2)
    b.refresh_from_db(), c.refresh_from_db()
    assert c.title == "Closing 2" and not c.missing_upstream and b.status == "scheduled"
    assert AuditLog.objects.filter(action="program.imported").count() == 5


def test_merge_removes_untouched_and_skips_bad_items(event):
    services.merge(event, "ical:1", [imported("x", "Gone soon", at(0), at(10)),
                                     imported("y", "Stays", at(0), at(10))])
    r = services.merge(event, "ical:1", [imported("y", "Stays", at(0), at(10)), imported("", "No id", at(0), at(5)),
                                         imported("z", "No duration", at(5), at(5)),
                                         imported("y", "Duplicate", at(0), at(10))])
    assert r.removed == 1 and not Session.objects.filter(external_id="x").exists()
    assert len(r.errors) == 2
    # another source's and local sessions are untouched
    assert services.merge(event, "ical:2", []).removed == 0
    assert Session.objects.filter(external_id="y").exists()


# ------------------------------------------------------------------ screens
def test_screen_payload_and_now_next(event, stages, talk, later, admin):
    hidden = services.save_session(Session(event=event, title="Crew briefing", stage=stages["ws"], public=False,
                                           starts_at=at(0), ends_at=at(10)), actor=admin)
    services.delay(later, 5, actor=admin)
    data = services.screen_payload(event)
    titles = [s["title"] for s in data["sessions"]]
    assert "Opening" in titles and "Crew briefing" not in titles
    lt = next(s for s in data["sessions"] if s["title"] == "Lightning talks")
    assert lt["delay"] == 5 and lt["planned_start"] and lt["stage_name"] == "Main stage"
    assert data["changes"][0]["kind"] == "delay"
    assert {s["name"] for s in data["stages"]} == {"Main stage", "Workshop"}
    assert services.now_next(event, stages["main"]) == (talk, later)
    assert hidden.pk


def test_player_api(client, admin, event, stages, talk):
    from apps.screens.tests.test_screen_ops import device, pair

    screen, token = pair(client, admin, event)
    screen.room = stages["main"].room
    screen.save()
    data = device(token).get("/player/api/schedule/").json()
    assert data["screen_room"] == str(stages["main"].room_id)
    assert data["sessions"][0]["title"] == "Opening"
    assert client.get("/player/api/schedule/").status_code == 401
    modules.set_event(event, "program", False)
    assert device(token).get("/player/api/schedule/").json()["sessions"] == []


def test_changes_push_to_screens(client, admin, event, talk, django_capture_on_commit_callbacks):
    from apps.screens import channel
    from apps.screens.tests.test_screen_ops import pair

    screen, _token = pair(client, admin, event)
    with mock.patch.object(channel, "send_many", return_value=1) as send, \
            django_capture_on_commit_callbacks(execute=True):
        services.delay(talk, 5, actor=admin)
    assert send.call_args[0][0] == [(screen.pk, "schedule.changed", {})]


# ------------------------------------------------------------------ anchors (ADR-0025)
def test_announcement_follows_its_session(event, talk, admin, django_capture_on_commit_callbacks):
    from apps.announcements import services as ann_services
    from apps.announcements.models import Announcement, Level

    ann_services.ensure_defaults(event)
    assert (str(talk.pk), mock.ANY) in services.anchor_choices(event)
    a = Announcement(event=event, level=Level.objects.get(event=event, key="info"), title="Opening soon",
                     channels=[ann_services.SCREENS], anchor=f"program:{talk.pk}", anchor_offset=-5)
    a = ann_services.save_draft(a, actor=admin)
    assert a.starts_at == talk.starts_at - dt.timedelta(minutes=5)
    with django_capture_on_commit_callbacks(execute=True):
        services.delay(talk, 20, actor=admin)
    a.refresh_from_db()
    assert a.starts_at == talk.starts_at - dt.timedelta(minutes=5)
    assert services.anchor_resolve(event, "not-a-uuid") is None


# ------------------------------------------------------------------ pages
@pytest.fixture
def staff(client, admin):
    return login_2fa(client, admin)


def test_index_and_live_actions(staff, event, stages, talk, later):
    base = f"/e/{event.slug}/schedule/"
    page = staff.get(base)
    assert page.status_code == 200 and b"Opening" in page.content and b"Main stage" in page.content
    r = staff.post(f"{base}{talk.pk}/live/", {"action": "delay", "minutes": "10", "following": "1"})
    assert r.status_code == 302 and "?day=" in r["Location"]
    talk.refresh_from_db()
    assert talk.delay_minutes == 10
    staff.post(f"{base}{talk.pk}/live/", {"action": "move", "stage": str(stages["ws"].pk)})
    staff.post(f"{base}{talk.pk}/live/", {"action": "cancel", "note": "Sorry"})
    talk.refresh_from_db()
    assert talk.status == "cancelled" and talk.note == "Sorry" and talk.stage == stages["ws"]
    staff.post(f"{base}{talk.pk}/live/", {"action": "restore"})
    staff.post(f"{base}{talk.pk}/live/", {"action": "reset"})
    r = staff.post(f"{base}{talk.pk}/live/", {"action": "delay", "minutes": "x"}, follow=True)
    assert b"minutes" in r.content
    r = staff.post(f"{base}{talk.pk}/live/", {"action": "nope"}, follow=True)
    assert b"Unknown action" in r.content
    assert staff.get(f"{base}?day=2020-01-01&stage={stages['main'].pk}").status_code == 200


def test_session_form_and_stages(staff, event, stages, talk):
    base = f"/e/{event.slug}/schedule/"
    assert staff.get(f"{base}new/").status_code == 200
    r = staff.post(f"{base}new/", {"title": "Panel", "starts_at": "2026-07-01T14:00", "ends_at": "2026-07-01T15:00",
                                   "stage": str(stages["ws"].pk), "speakers_text": "Ada, Grace", "public": "on"})
    assert r.status_code == 302
    panel = Session.objects.get(title="Panel")
    assert sorted(p.name for p in panel.speakers.all()) == ["Ada", "Grace"]
    assert panel.starts_at.hour == 12  # Europe/Berlin in summer
    r = staff.post(f"{base}{panel.pk}/", {"title": "Panel", "starts_at": "2026-07-01T15:00",
                                          "ends_at": "2026-07-01T14:00"})
    assert r.status_code == 200 and b"end" in r.content
    assert staff.get(f"{base}{panel.pk}/").status_code == 200
    staff.post(f"{base}{panel.pk}/delete/")
    assert not Session.objects.filter(title="Panel").exists()

    assert staff.get(f"{base}stages/").status_code == 200
    staff.post(f"{base}stages/", {"what": "stage", "stage-name": "Tent", "stage-order": "3"})
    staff.post(f"{base}stages/", {"what": "track", "track-name": "Food", "track-colour": "#16a34a"})
    tent = Stage.objects.get(name="Tent")
    staff.post(f"{base}stages/{tent.pk}/delete/")
    assert not Stage.objects.filter(name="Tent").exists()
    assert AuditLog.objects.filter(action__in=["program.stage_created", "program.track_created",
                                               "program.stage_deleted"]).count() == 3


def test_imported_session_edit_records_overrides(staff, event, admin):
    services.merge(event, "frab:1", [imported("a", "Opening", at(0), at(30), speakers=[("p", "Ada")])])
    s = Session.objects.get(external_id="a")
    local = timezone_local(s, event)
    staff.post(f"/e/{event.slug}/schedule/{s.pk}/", {
        "title": "Opening (local)", "starts_at": local(s.starts_at), "ends_at": local(s.ends_at),
        "speakers_text": "Ada, Bob", "public": "on"})
    s.refresh_from_db()
    assert set(s.overrides) == {"title", "speakers"}


def timezone_local(s, event):
    import zoneinfo

    tz = zoneinfo.ZoneInfo(event.timezone)
    return lambda d: d.astimezone(tz).strftime("%Y-%m-%dT%H:%M")


def test_permissions_and_module_switch(client, event, member, talk):
    login_2fa(client, member)
    base = f"/e/{event.slug}/schedule/"
    assert client.get(base).status_code == 200  # viewers see the program
    assert client.post(f"{base}{talk.pk}/live/", {"action": "cancel"}).status_code == 403
    assert client.get(f"{base}new/").status_code == 403
    modules.set_event(event, "program", False)
    assert client.get(base).status_code == 404


def test_public_page_and_exports(client, event, stages, talk, later, admin):
    url = f"/public/{event.slug}/program/"
    assert client.get(url).status_code == 404  # off by default
    settings_store.save("program", "event", str(event.pk), {"public_page": True}, event=event)
    services.save_session(Session(event=event, title="Secret", starts_at=at(0), ends_at=at(5), public=False),
                          actor=admin)
    services.cancel(later, actor=admin)
    page = client.get(url)
    assert page.status_code == 200 and b"Opening" in page.content and b"Secret" not in page.content
    assert b"Cancelled" in page.content
    ics = client.get(f"/public/{event.slug}/program.ics")
    body = ics.content.decode()
    assert ics["Content-Type"].startswith("text/calendar") and "SUMMARY:Opening" in body
    assert "STATUS:CANCELLED" in body and all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    data = client.get(f"/public/{event.slug}/program.json").json()
    assert data["event"]["name"] == event.name and "Secret" not in {x["title"] for x in data["sessions"]}
    xml = client.get(f"/public/{event.slug}/schedule.xml")
    assert b"<schedule>" in xml.content and b"Opening" in xml.content
    # the exported frab XML and JSON read back with the importers
    from extensions.program_import import parse

    assert {i.title for i in parse.frab_xml(xml.content, "UTC")} >= {"Opening"}
    assert {i.title for i in parse.ical(ics.content, "UTC")} >= {"Opening"}
    modules.set_event(event, "program", False)
    assert client.get(url).status_code == 404


def test_frab_export_days(event, stages, admin):
    services.save_session(Session(event=event, title="Late night", stage=stages["main"],
                                  starts_at=dt.datetime(2026, 7, 2, 1, 0, tzinfo=dt.UTC),
                                  ends_at=dt.datetime(2026, 7, 2, 2, 0, tzinfo=dt.UTC)), actor=admin)
    xml = exports.frab(event).decode()
    assert "Late night" in xml and 'date="2026-07-01"' in xml  # 03:00 Berlin belongs to the day before


# ------------------------------------------------------------------ API
@pytest.fixture
def api(event, admin):
    tok, raw = ServiceToken.issue(owner=admin, name="stage", scopes=["program:read", "program:write"], event=event)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    return c


def test_api_list_and_live(api, event, stages, talk):
    base = f"/api/v1/events/{event.slug}/sessions/"
    rows = api.get(base).json()
    rows = rows.get("results", rows) if isinstance(rows, dict) else rows
    assert rows[0]["title"] == "Opening" and rows[0]["stage_name"] == "Main stage"
    day = talk.starts_at.date().isoformat()
    assert api.get(base, {"day": "x"}).status_code == 400
    assert api.get(base, {"day": "2020-01-01"}).json() in ([], {"count": 0, "next": None, "previous": None,
                                                                 "results": []})
    assert api.get(base, {"day": day}).status_code == 200
    r = api.post(f"{base}{talk.pk}/live/", {"action": "delay", "minutes": 7, "shift_following": True},
                 format="json")
    assert r.status_code == 200 and r.json()["delay_minutes"] == 7
    r = api.post(f"{base}{talk.pk}/live/", {"action": "move", "stage": str(stages["ws"].pk)}, format="json")
    assert r.json()["stage_name"] == "Workshop"
    r = api.post(f"{base}{talk.pk}/live/", {"action": "move", "stage": str(talk.pk)}, format="json")
    assert r.status_code == 400
    assert api.post(f"{base}{talk.pk}/live/", {"action": "cancel"}, format="json").json()["status"] == "cancelled"
    assert api.post(f"{base}{talk.pk}/live/", {"action": "cancel"}, format="json").status_code == 400
    assert api.post(f"{base}{talk.pk}/live/", {"action": "restore"}, format="json").json()["status"] == "scheduled"
    modules.set_event(event, "program", False)
    assert api.get(base).status_code == 404


def test_api_needs_live_permission(event, member, talk):
    tok, raw = ServiceToken.issue(owner=member, name="viewer", scopes=["program:read", "program:write"], event=event)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    base = f"/api/v1/events/{event.slug}/sessions/"
    assert c.get(base).status_code == 200
    assert c.post(f"{base}{talk.pk}/live/", {"action": "cancel"}, format="json").status_code == 403


# ------------------------------------------------------------------ editor, sync, a11y
def test_editor_offers_program_choices(event, stages, talk):
    from apps.content import layout_format
    from apps.content.layout_views import editor_choices

    assert "program" in layout_format.ELEMENT_TYPES
    choices = editor_choices(event)
    assert {c["label"] for c in choices["programStages"]} == {"Main stage", "Workshop"}
    assert choices["programData"]["sessions"][0]["title"] == "Opening"
    modules.set_event(event, "program", False)
    assert "programData" not in editor_choices(event)


def test_pages_are_accessible(staff, event, stages, talk):
    settings_store.save("program", "event", str(event.pk), {"public_page": True}, event=event)
    for url in (f"/e/{event.slug}/schedule/", f"/e/{event.slug}/schedule/new/", f"/e/{event.slug}/schedule/stages/",
                f"/e/{event.slug}/schedule/{talk.pk}/", f"/public/{event.slug}/program/"):
        assert audit_url(staff, url) == [], url


def test_demo_seed(event, admin, venue):
    from apps.schedule import demo
    from apps.venues.models import Room

    Room.objects.create(venue=venue, name="Workshop 1")
    assert demo.seed(event, admin) == len(demo.TALKS)
    assert demo.seed(event, admin) == 0
    assert Stage.objects.get(event=event, name="Main stage").room.name == "Hall A"
    assert Session.objects.filter(event=event, planned_start__isnull=False).count() == 2
