# SPDX-License-Identifier: AGPL-3.0-or-later
"""Occupancy: counting from several devices and sensors, the capacity rule with hysteresis, "full" on screens,
alerts, history, the door counter and the API (roadmap 6.3, ADR-0040)."""
import datetime as dt
import json
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken, User
from apps.core import modules
from apps.core.a11y import audit_url
from apps.core.models import AuditLog, Notification
from apps.crowd import panels, sensors, services
from apps.crowd.models import Area, CountEvent, Sample
from apps.events import services as ev
from conftest import login_2fa


@pytest.fixture
def hall(event, venue, role):
    from apps.venues.models import Room

    alt = services.save_area(Area(event=event, name="Hall B", room=Room.objects.get(name="Hall B"), capacity=300),
                             actor=None)
    a = Area(event=event, name="Hall A", room=Room.objects.get(name="Hall A"), capacity=10, busy_percent=80,
             full_percent=100, release_percent=80, alternative=alt, channels=[])
    return services.save_area(a, actor=None, m2m={"notify_roles": [role("control-room")]})


@pytest.fixture
def control(event, role):
    u = User.objects.create_user(email="control@example.org", password="pw-control-123")
    ev.assign_role(event, u, role("control-room"))
    return u


def test_rule_with_hysteresis(hall):
    s = services.state_for
    assert [s(hall, v, "normal") for v in (0, 7, 8, 9, 10, 12)] == ["normal", "normal", "busy", "busy", "full",
                                                                       "full"]
    assert s(hall, 9, "full") == "full" and s(hall, 8, "full") == "full" and s(hall, 7, "full") == "normal"
    hall.capacity = 0
    assert s(hall, 999, "full") == "normal"


def test_counting_from_several_sources(hall, control, django_capture_on_commit_callbacks):
    with mock.patch.object(services, "push_screens") as push:
        with django_capture_on_commit_callbacks(execute=True):
            services.count(hall, 6, source="clicker", device="Door A", client_id="a1")
            services.count(hall, 6, source="clicker", device="Door A", client_id="a1")  # replay
            assert hall.value == 6 and hall.state == "normal"
            services.count(hall, 2, source="clicker", device="Door B")
            assert hall.state == "busy"
        assert not push.called
        with django_capture_on_commit_callbacks(execute=True):
            services.count(hall, 2, source="sensor")
            assert hall.state == "full"
        assert push.called
    assert Notification.objects.filter(user=control, title__contains="Hall A is full (10 / 10)").exists()
    assert AuditLog.objects.filter(action="crowd.full").exists()
    services.count(hall, -50, source="clicker")
    hall.refresh_from_db()
    assert hall.value == 0 and hall.state == "normal"
    with pytest.raises(ValidationError):
        services.count(hall, 20_000, source="api")
    assert CountEvent.objects.filter(area=hall).count() == 4
    assert CountEvent.objects.filter(source="clicker", user__isnull=False).count() == 0  # anonymous clicks


def test_correction_and_reset(hall, admin, event):
    services.set_value(hall, 9, source=CountEvent.Source.CORRECTION, actor=admin)
    c = CountEvent.objects.get(source="correction")
    assert c.user == admin and c.delta == 9
    assert AuditLog.objects.filter(action="crowd.corrected").exists()
    with pytest.raises(ValidationError):
        services.set_value(hall, -1, source="sensor")
    assert services.reset_all(event, actor=admin) == 1
    hall.refresh_from_db()
    assert hall.value == 0


def test_full_banner_on_screens(hall, event, client, admin):
    from apps.playlists.services import Target
    from apps.screens.models import Screen, ScreenGroup
    from apps.screens.tests.test_screen_ops import pair

    screen, _token = pair(client, admin, event, name="Hall A door")
    screen.room = hall.room
    screen.save()
    other, _t = pair(client, admin, event, name="Foyer")
    now = timezone.now()
    services.count(hall, 10, source="sensor")
    out = services.program_source(event, Target(screen=screen), now, now)
    banner = out["overlays"][0]
    assert banner["style"] == "banner" and banner["text"] == "Hall A is full. Please use Hall B."
    assert banner["windows"] == [[None, None]]
    assert services.program_source(event, Target(screen=other), now, now)["overlays"] == []
    group = ScreenGroup.objects.create(event=event, name="Foyer screens")
    other.manual_groups.add(group)
    hall.screen_groups.add(group)
    assert services.program_source(event, Target(screen=Screen.objects.get(pk=other.pk)), now, now)["overlays"]
    assert services.program_source(event, Target(group=group), now, now)["overlays"]
    # the alternative is full too: no suggestion; a custom text wins
    alt = hall.alternative
    services.count(alt, 300, source="sensor")
    hall.refresh_from_db()
    assert "Please wait" in services.suggestion(hall)
    hall.full_text = "Hall A is full - next show at 20:00"
    assert services.suggestion(hall) == "Hall A is full - next show at 20:00"
    hall.show_on_screens = False
    hall.save()
    assert services.program_source(event, Target(screen=screen), now, now)["overlays"] == []
    modules.set_event(event, "crowd", False)
    assert services.program_source(event, Target(screen=screen), now, now)["overlays"] == []


def test_full_pushes_to_player(hall, event, client, admin, django_capture_on_commit_callbacks):
    from apps.screens import channel
    from apps.screens.tests.test_screen_ops import device, pair

    screen, token = pair(client, admin, event)
    screen.room = hall.room
    screen.save()
    with mock.patch.object(channel, "send_many", return_value=1) as send, \
            django_capture_on_commit_callbacks(execute=True):
        services.count(hall, 10, source="sensor")
    assert send.call_args[0][0] == [(screen.pk, "program.changed", {})]
    program = device(token).get("/player/api/playlists/program/").json()["program"]
    assert any(o["id"] == f"crowd:{hall.pk}" for o in program["overlays"])


def test_history_and_chart(hall):
    now = timezone.now().replace(second=0, microsecond=0)
    for m, v in ((90, 2), (60, 5), (30, 9)):
        Sample.objects.create(area=hall, minute=now - dt.timedelta(minutes=m), value=v, peak=v + 1, low=v - 1)
    services.count(hall, 4, source="clicker")
    services.count(hall, 1, source="clicker")
    s = Sample.objects.filter(area=hall).order_by("-minute").first()
    assert (s.value, s.peak, s.low) == (5, 5, 4)
    samples = services.history(hall, hours=2)
    chart = services.chart(hall, samples, hours=2)
    assert chart["peak"] == 10 and len(chart["lines"]) == 2 and chart["points"].count(",") > 6
    assert chart["ticks"]


def test_area_validation(event, admin):
    with pytest.raises(ValidationError, match="name"):
        services.save_area(Area(event=event, name=""), actor=admin)
    with pytest.raises(ValidationError, match="Busy"):
        services.save_area(Area(event=event, name="x", capacity=10, busy_percent=120, full_percent=100), actor=admin)
    a = services.save_area(Area(event=event, name="Tent", capacity=10), actor=admin)
    a.alternative = a
    with pytest.raises(ValidationError, match="itself"):
        services.save_area(a, actor=admin)


def test_capacity_change_reevaluates(hall, admin, django_capture_on_commit_callbacks):
    services.count(hall, 9, source="sensor")
    hall.capacity = 9
    with django_capture_on_commit_callbacks(execute=True):
        services.save_area(hall, actor=admin)
    assert hall.state == "full"
    services.delete_area(hall, actor=admin)
    assert not Area.objects.filter(name="Hall A").exists()


# ------------------------------------------------------------------ sensors
@pytest.mark.parametrize("body,expect", [
    ({"delta": 3}, ("delta", 3, "")), ({"in": 5, "out": 2, "id": "m1"}, ("delta", 3, "m1")),
    ({"out": 2}, ("delta", -2, "")), ({"value": 42}, ("value", 42, "")), (17, ("value", 17, "")),
])
def test_parse(body, expect):
    assert sensors.parse(body) == expect


@pytest.mark.parametrize("body", [True, "x", {"delta": "3"}, {"nothing": 1}, [1], {"in": True}])
def test_parse_rejects(body):
    with pytest.raises(ValidationError):
        sensors.parse(body)


def test_mqtt(hall, event):
    hall.sensor_key = "hall-a"
    hall.save()
    sensors.mqtt_handler(f"crowd/{event.slug}/hall-a", b'{"in": 4, "out": 1, "id": "x"}')
    sensors.mqtt_handler(f"crowd/{event.slug}/hall-a", b'{"in": 4, "out": 1, "id": "x"}')
    sensors.mqtt_handler(f"crowd/{event.slug}/hall-a", b"not json")
    sensors.mqtt_handler(f"crowd/{event.slug}/unknown", b"5")
    sensors.mqtt_handler("other/topic", b"5")
    hall.refresh_from_db()
    assert hall.value == 3
    sensors.mqtt_handler(f"crowd/{event.slug}/hall-a", b"8")
    hall.refresh_from_db()
    assert hall.value == 8 and CountEvent.objects.filter(source="mqtt").count() == 2


def test_mqtt_dispatch(hall, event):
    from extensions.mqtt import client

    assert client.topic_matches("crowd/+/+", "crowd/demo/x") and not client.topic_matches("crowd/+/+", "crowd/demo")
    assert client.topic_matches("a/#", "a/b/c") and not client.topic_matches("a/b", "a/c")
    hall.sensor_key = "s1"
    hall.save()
    assert client.dispatch(f"evac/crowd/{event.slug}/s1", b"4", "evac")
    assert not client.dispatch("evac/bridge/x/input", b"{}", "evac")
    assert not client.dispatch("other/crowd/x/y", b"4", "evac")
    assert ("evac/crowd/+/+", 1) in client.subscriptions("evac")
    hall.refresh_from_db()
    assert hall.value == 4


# ------------------------------------------------------------------ pages
@pytest.fixture
def staff(client, admin):
    return login_2fa(client, admin)


def test_pages(staff, event, hall, venue):
    from apps.venues.models import Room

    base = f"/e/{event.slug}/crowd/"
    assert b"Hall A" in staff.get(base).content
    r = staff.post(base, {"name": "Foyer", "room": str(Room.objects.get(name="Hall B").pk), "capacity": "",
                          "busy_percent": "80", "full_percent": "100", "release_percent": "90",
                          "show_on_screens": "on", "order": "0"})
    assert r.status_code == 302 and Area.objects.get(name="Foyer").capacity == 300  # the room's capacity
    assert staff.post(base, {"name": "Both", "room": str(Room.objects.get(name="Hall B").pk),
                             "zone": str(hall.room.zones.first().pk), "busy_percent": "80", "full_percent": "100",
                             "release_percent": "90", "order": "0"}).status_code == 200
    page = staff.get(f"{base}{hall.pk}/?hours=6")
    assert page.status_code == 200 and b"<polyline" in page.content
    staff.post(f"{base}{hall.pk}/", {"what": "correct", "value": "4"})
    hall.refresh_from_db()
    assert hall.value == 4
    staff.post(f"{base}{hall.pk}/", {"name": "Hall A", "capacity": "20", "busy_percent": "80",
                                     "full_percent": "100", "release_percent": "90", "order": "1"})
    hall.refresh_from_db()
    assert hall.capacity == 20
    staff.post(base, {"what": "reset"})
    hall.refresh_from_db()
    assert hall.value == 0
    staff.post(f"{base}{hall.pk}/", {"what": "delete"})
    assert not Area.objects.filter(pk=hall.pk).exists()


def test_counter_batch(staff, event, hall):
    url = f"/e/{event.slug}/crowd/count/"
    page = staff.get(f"{url}{hall.pk}/")
    assert b"data-counter" in page.content
    batch = {"counts": [{"area": str(hall.pk), "delta": 1, "id": f"c{i}", "device": "Door A",
                         "at": timezone.now().isoformat()} for i in range(10)]}
    r = staff.post(url, json.dumps(batch), content_type="application/json")
    assert r.json()["areas"][str(hall.pk)] == {"value": 10, "capacity": 10, "percent": 100, "state": "full",
                                               "label": "Full"}
    r = staff.post(url, json.dumps(batch), content_type="application/json")  # the same clicks again
    assert r.json()["areas"][str(hall.pk)]["value"] == 10
    bad = {"counts": [{"area": "nope", "delta": 1}, {"area": str(hall.pk), "delta": 500},
                      {"area": str(hall.pk), "delta": True}, "x"]}
    assert staff.post(url, json.dumps(bad), content_type="application/json").json()["refused"] == 3
    assert staff.post(url, "nope", content_type="application/json").status_code == 400
    assert staff.get(f"/e/{event.slug}/crowd/{hall.pk}/state.json").json()["state"] == "full"


def test_permissions(client, event, hall, member, role):
    login_2fa(client, member)  # viewer: sees, cannot count or manage
    assert client.get(f"/e/{event.slug}/crowd/").status_code == 200
    assert client.get(f"/e/{event.slug}/crowd/count/{hall.pk}/").status_code == 403
    assert client.post(f"/e/{event.slug}/crowd/", {"what": "reset"}).status_code == 403
    crew = User.objects.create_user(email="door@example.org", password="pw-door-123456")
    ev.assign_role(event, crew, role("crew"))
    crew_role = role("crew")
    crew_role.permissions = [*crew_role.permissions, "crowd.count"]
    crew_role.save()
    login_2fa(client, crew)
    assert client.get(f"/e/{event.slug}/crowd/count/{hall.pk}/").status_code == 200
    assert b"Door counter" in client.get(f"/e/{event.slug}/staff/").content
    modules.set_event(event, "crowd", False)
    assert client.get(f"/e/{event.slug}/crowd/count/{hall.pk}/").status_code == 404


def test_pages_are_accessible(staff, event, hall):
    for url in ("", f"{hall.pk}/", f"count/{hall.pk}/"):
        assert audit_url(staff, f"/e/{event.slug}/crowd/{url}") == [], url


def test_panels_and_data_source(hall, event):
    services.count(hall, 9, source="sensor")
    data = panels.data_source(event)
    row = next(i for i in data["items"] if i["name"] == "Hall A")
    assert row["percent"] == 90 and row["free"] == 1 and row["state"] == "busy"
    assert data["total"] == 9


# ------------------------------------------------------------------ API
def test_api(event, admin, hall):
    _tok, raw = ServiceToken.issue(name="cam-a", owner=admin, scopes=["crowd:read", "crowd:write"], event=event)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    base = f"/api/v1/events/{event.slug}/occupancy/"
    rows = c.get(base).json()
    assert any(r["name"] == "Hall A" for r in (rows.get("results", rows) if isinstance(rows, dict) else rows))
    assert c.post(f"{base}{hall.pk}/count/", {"in": 6, "out": 1, "id": "m1"}, format="json").json()["value"] == 5
    assert c.post(f"{base}{hall.pk}/count/", {"in": 6, "out": 1, "id": "m1"}, format="json").json()["value"] == 5
    assert c.post(f"{base}{hall.pk}/count/", {"value": 10}, format="json").json()["state"] == "full"
    assert c.post(f"{base}{hall.pk}/count/", {"delta": 1}, format="json").json()["value"] == 11
    assert c.post(f"{base}{hall.pk}/count/", {}, format="json").status_code == 400
    assert c.post(f"{base}{hall.pk}/count/", {"in": "x"}, format="json").status_code == 400
    assert CountEvent.objects.filter(source="sensor", device="cam-a").count() == 3
    modules.set_event(event, "crowd", False)
    assert c.get(base).status_code == 404


def test_demo_seed(event, admin, venue):
    from apps.crowd import demo
    from apps.venues.models import Room

    Room.objects.create(venue=venue, name="Beer garden", capacity=500)
    assert demo.seed(event, admin) == 4
    assert demo.seed(event, admin) == 0
    assert Sample.objects.filter(area__name="Hall A").count() > 40
