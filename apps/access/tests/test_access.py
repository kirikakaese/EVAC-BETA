# SPDX-License-Identifier: AGPL-3.0-or-later
"""Access (ADR-0044): scanner rules, offline batches and replays, presence, the occupancy feed, import/export,
badges, pages, permissions and the API."""
import datetime as dt
import json
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.access import badges, panels, services
from apps.access.models import AccessZone, Attendee, Presence, Scan, TicketType
from apps.core import modules
from apps.core.a11y import check_html
from conftest import login_2fa

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(event, admin):
    entrance = AccessZone.objects.create(event=event, name="Main entrance", open_to_all=True, checkin=True)
    backstage = AccessZone.objects.create(event=event, name="Backstage", reentry=False)
    day = TicketType.objects.create(event=event, name="Day ticket")
    crew = TicketType.objects.create(event=event, name="Crew", colour="#16a34a")
    crew.zones.add(backstage)
    ada = services.save_attendee(Attendee(event=event, name="Ada", ticket_type=day, code="ADA-1"), actor=admin)
    bob = services.save_attendee(Attendee(event=event, name="Bob", ticket_type=crew, code="BOB-1"), actor=admin)
    return {"entrance": entrance, "backstage": backstage, "day": day, "crew": crew, "ada": ada, "bob": bob}


def test_rules(setup, admin):
    e, b, ada, bob = setup["entrance"], setup["backstage"], setup["ada"], setup["bob"]
    with mock.patch("apps.core.webhooks.emit"):
        s, msg = services.scan(e, "ADA-1", actor=admin)
    assert s.result == "ok" and msg == "Welcome, Ada"
    ada.refresh_from_db()
    assert ada.checked_in_at is not None and Presence.objects.get(attendee=ada, zone=e).inside
    assert services.scan(e, "ADA-1", actor=admin)[0].result == "ok"  # re-entry allowed at the entrance
    assert services.scan(b, "ADA-1", actor=admin)[0].result == "denied"
    assert services.scan(b, "BOB-1", actor=admin)[0].result == "ok"
    assert services.scan(b, "BOB-1", actor=admin)[0].result == "duplicate"  # no re-entry backstage
    assert services.scan(b, "BOB-1", direction="out", actor=admin)[1] == "Goodbye, Bob"
    assert services.scan(b, "BOB-1", actor=admin)[0].result == "ok"
    s, _m = services.scan(e, "NOPE-9999", actor=admin)
    assert s.result == "unknown" and s.code_hint == "9999"
    services.set_status(bob, "blocked", actor=admin)
    assert services.scan(e, "BOB-1", actor=admin)[0].result == "invalid"
    with pytest.raises(ValidationError):
        services.set_status(bob, "nope", actor=admin)


def test_batch_replays_offline_times_and_cross_device_duplicates(setup, admin):
    b = setup["backstage"]
    earlier = (timezone.now() - dt.timedelta(minutes=5)).isoformat()
    items = [{"id": "dev1-1", "zone": str(b.pk), "code": "BOB-1", "dir": "in", "at": earlier, "device": "Gate A",
              "offline": True},
             {"id": "dev2-1", "zone": str(b.pk), "code": "BOB-1", "dir": "in", "device": "Gate B", "offline": True},
             {"id": "x", "zone": "00000000-0000-0000-0000-000000000000", "code": "BOB-1"}, "junk"]
    out = services.batch(b.event, items, actor=admin, can_scan=lambda z: True)
    assert [r["result"] for r in out] == ["ok", "duplicate", "refused"]
    s = Scan.objects.get(client_id="dev1-1")
    assert s.offline and s.device == "Gate A" and abs((s.at - dt.datetime.fromisoformat(earlier)).total_seconds()) < 1
    again = services.batch(b.event, items[:2], actor=admin, can_scan=lambda z: True)  # the answer got lost
    assert [r["result"] for r in again] == ["ok", "duplicate"] and Scan.objects.count() == 2
    refused = services.batch(b.event, items[:1], actor=admin, can_scan=lambda z: False)
    assert refused[0]["result"] == "refused"


def test_occupancy_feed(setup, admin, event):
    from apps.crowd.models import Area, CountEvent

    area = Area.objects.create(event=event, name="Site", capacity=100)
    e = setup["entrance"]
    e.area_id = area.pk
    e.save()
    services.scan(e, "ADA-1", actor=admin, device="Gate 1")
    services.scan(e, "ADA-1", actor=admin)  # re-entry while inside: no second count
    services.scan(e, "BOB-1", actor=admin)
    area.refresh_from_db()
    assert area.value == 2
    assert CountEvent.objects.filter(area=area, source="scanner").count() == 2
    services.scan(e, "ADA-1", direction="out", actor=admin)
    area.refresh_from_db()
    assert area.value == 1
    modules.set_instance("crowd", False)
    services.scan(e, "ADA-1", actor=admin)
    area.refresh_from_db()
    assert area.value == 1


def test_offline_list_hashes_codes(setup):
    data = services.offline_list(setup["backstage"])
    assert services.code_key("BOB-1") in data["tickets"] and "BOB-1" not in json.dumps(data)
    assert data["zone"]["allowed"] == [str(setup["crew"].pk)] and data["zone"]["reentry"] is False
    name, type_id, valid, inside = data["tickets"][services.code_key("ADA-1")]
    assert (name, valid, inside) == ("Ada", 1, 0)
    assert len(services.offline_list(setup["entrance"])["zone"]["allowed"]) == 2


def test_import_and_export(client, setup, admin, event):
    raw = (b"name,email,ticket_type,code\nCarla,c@x.org,VIP,CARLA-1\nAda Updated,,Day ticket,ADA-1\n,,x,\n"
           b"Dora,,Day ticket,\n")
    st = services.import_csv(event, raw, actor=admin)
    assert st == {"added": 2, "updated": 1, "skipped": 1, "types": 1}
    assert Attendee.objects.get(code="ADA-1").name == "Ada Updated"
    assert len(Attendee.objects.get(name="Dora").code) >= 10
    with pytest.raises(ValidationError):
        services.import_csv(event, b"foo,bar\n1,2", actor=admin)
    with pytest.raises(ValidationError):
        services.import_csv(event, b"\xff\xfe", actor=admin)
    services.save_attendee(Attendee(event=event, name="=HYPERLINK(1)", ticket_type=setup["day"]), actor=admin)
    c = login_2fa(client, admin)
    body = c.get(f"/e/{event.slug}/access/export.csv").content.decode()
    assert "CARLA-1" in body and "'=HYPERLINK" in body
    from django.core.files.uploadedfile import SimpleUploadedFile

    r = c.post(f"/e/{event.slug}/access/import/", {"file": SimpleUploadedFile(
        "a.csv", b"name,ticket_type\nEve,Crew\n", "text/csv")})
    assert r.status_code == 302 and Attendee.objects.filter(name="Eve").exists()
    with pytest.raises(ValidationError, match="taken"):
        services.save_attendee(Attendee(event=event, name="Dup", ticket_type=setup["day"], code="ADA-1"),
                               actor=admin)


def test_badges(client, setup, admin, event):
    c = login_2fa(client, admin)
    page = c.get(f"/e/{event.slug}/access/badges/").content.decode()
    assert page.count('class="badge-card"') == 2 and check_html(page) == []
    layout = badges.create_layout(setup["crew"], actor=admin)
    assert not layout.is_default and setup["crew"].badge_layout == layout
    from apps.content import layout_format as lf

    assert lf.validate(layout.data) == []
    page = c.get(f"/e/{event.slug}/access/badges/?type={setup['crew'].pk}").content.decode()
    assert "data-preview-pages" in page and "BOB-1" in page and check_html(page) == []
    cfg = badges.sheet_config(event, layout, [setup["bob"]])
    assert cfg["pages"][0]["attendee"]["code"] == "BOB-1" and cfg["pageLabels"] == ["Badge of Bob"]
    r = c.post(f"/e/{event.slug}/access/badges/?new=1")
    assert r.status_code == 302 and not Attendee.objects.filter(badge_printed_at__isnull=True).exists()
    r = c.post(f"/e/{event.slug}/access/types/{setup['day'].pk}/", {"badge": "create"})
    assert r.status_code == 302 and "/content/layouts/" in r.url


def test_pages(client, setup, admin, event):
    c = login_2fa(client, admin)
    services.scan(setup["entrance"], "ADA-1", actor=admin)
    base = f"/e/{event.slug}/access/"
    for url in ["", "?q=ada&type=" + str(setup["day"].pk) + "&status=in", "?status=out", "?status=blocked",
                "attendees/new/", f"attendees/{setup['ada'].pk}/", "types/", f"types/{setup['day'].pk}/",
                f"zones/{setup['backstage'].pk}/", "import/", "scan/", f"scan/{setup['entrance'].pk}/",
                f"scan/{setup['entrance'].pk}/?dir=out"]:
        r = c.get(base + url)
        assert r.status_code == 200, url
        assert check_html(r.content.decode()) == [], url
    r = c.post(base + "attendees/new/", {"name": "Neo", "ticket_type": setup["day"].pk})
    assert r.status_code == 302 and Attendee.objects.get(name="Neo").code
    c.post(f"{base}attendees/{setup['ada'].pk}/", {"status": "cancelled"})
    assert Attendee.objects.get(pk=setup["ada"].pk).status == "cancelled"
    c.post(base + "types/", {"what": "type", "t-name": "VIP", "t-colour": "#000000", "t-order": 0})
    c.post(base + "types/", {"what": "zone", "z-name": "Lounge", "z-order": 0})
    assert TicketType.objects.filter(name="VIP").exists() and AccessZone.objects.filter(name="Lounge").exists()
    c.post(f"{base}types/{setup['day'].pk}/", {"delete": "1"})
    assert TicketType.objects.filter(pk=setup["day"].pk).exists()  # still has attendees
    lst = c.get(f"{base}scan/{setup['entrance'].pk}/list/").json()
    assert lst["count"] == 3 and lst["tickets"][services.code_key("ADA-1")][2] == 0
    r = c.post(f"{base}scan/sync/", json.dumps({"scans": [{"id": "s1", "zone": str(setup["entrance"].pk),
                                                           "code": "BOB-1"}]}), content_type="application/json")
    assert r.json()["results"][0]["result"] == "ok"
    assert c.post(f"{base}scan/sync/", "nope", content_type="application/json").status_code == 400
    assert b"Main entrance" in c.get(f"/e/{event.slug}/staff/").content
    assert c.get(f"/e/{event.slug}/ops/control/").status_code == 200


def test_permissions_and_scoped_scanner(client, setup, event, user, member, role):
    from apps.events import services as ev

    client.force_login(user)  # viewer: sees, may not scan or manage
    assert client.get(f"/e/{event.slug}/access/").status_code == 200
    assert client.get(f"/e/{event.slug}/access/scan/{setup['entrance'].pk}/").status_code == 403
    assert client.get(f"/e/{event.slug}/access/types/{setup['day'].pk}/").status_code == 403
    assert client.get(f"/e/{event.slug}/access/export.csv").status_code == 403
    scanner_role = event.roles.create(key="gate", name="Gate", permissions=["access.scan", "events.view"])
    ev.assign_role(event, user, scanner_role, scope_kind="access_zone", scope_id=str(setup["entrance"].pk))
    assert client.get(f"/e/{event.slug}/access/scan/{setup['entrance'].pk}/").status_code == 200
    assert client.get(f"/e/{event.slug}/access/scan/{setup['backstage'].pk}/").status_code == 403
    out = client.post(f"/e/{event.slug}/access/scan/sync/", json.dumps({"scans": [
        {"id": "a", "zone": str(setup["entrance"].pk), "code": "ADA-1"},
        {"id": "b", "zone": str(setup["backstage"].pk), "code": "BOB-1"}]}), content_type="application/json").json()
    assert [r["result"] for r in out["results"]] == ["ok", "refused"]
    modules.set_instance("access", False)
    assert client.get(f"/e/{event.slug}/access/").status_code == 404


def test_sources_and_panels(setup, admin, event):
    services.scan(setup["entrance"], "ADA-1", actor=admin)
    src = panels.zones_source(event)
    assert src["checked_in"] == 1 and {"title": "Main entrance", "value": 1} in src["items"]
    assert {z for z, _n in panels.zone_choices(event)} == {str(setup["entrance"].pk), str(setup["backstage"].pk)}


def test_api(client, setup, admin, event):
    c = login_2fa(client, admin)
    base = f"/api/v1/events/{event.slug}/"
    r = c.post(base + "attendees/", {"name": "Api", "ticket_type": str(setup["day"].pk)},
               content_type="application/json")
    assert r.status_code == 201 and r.json()["code"]
    pk = r.json()["id"]
    assert c.patch(f"{base}attendees/{pk}/", {"company": "ACME"}, content_type="application/json").json()[
        "company"] == "ACME"
    r = c.post(base + "attendees/", {"name": "Dup", "ticket_type": str(setup["day"].pk), "code": "ADA-1"},
               content_type="application/json")
    assert r.status_code == 400
    assert c.get(base + "attendees/?search=Ada").json()["count"] == 1
    assert c.get(base + "ticket-types/").json()["count"] == 2
    r = c.post(f"{base}access-zones/{setup['entrance'].pk}/scan/", {"code": "ADA-1", "id": "t1"},
               content_type="application/json")
    assert r.json() == {"result": "ok", "message": "Welcome, Ada", "name": "Ada"}
    assert c.post(f"{base}access-zones/{setup['entrance'].pk}/scan/", {}, content_type="application/json"
                  ).status_code == 400
    zones = c.get(base + "access-zones/").json()["results"]
    assert [z["inside"] for z in zones if z["name"] == "Main entrance"] == [1]
