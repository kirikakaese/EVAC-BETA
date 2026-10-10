# SPDX-License-Identifier: AGPL-3.0-or-later
"""Propagation and acknowledgements (roadmap 3.8): screens reached, p95 latency, staff answers."""
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.core import settings_store
from apps.core.a11y import check_html
from apps.core.models import AuditLog, Notification
from apps.evacuation import acks, feed, services
from apps.evacuation.models import LatencySample, ScreenAck, StaffAck
from apps.screens.models import Screen

from .conftest import tf

URL = "/e/demo/evacuation/"


def _screen(event, venue, name, *, zone=None, room=None, health="online"):
    s = Screen.objects.create(event=event, name=name, venue=venue, zone=zone, room=room)
    s.issue_token()
    s.health_state = health
    s.save()
    return s


@pytest.fixture
def screens(event, venue, zones):
    from apps.venues.models import Room

    return {"a": _screen(event, venue, "A", zone=zones["North"]),
            "b": _screen(event, venue, "B", room=Room.objects.get(name="Hall B")),
            "c": _screen(event, venue, "C", zone=zones["North"], health="offline"),
            "d": _screen(event, venue, "D", health="stale"),
            "x": _screen(event, venue, "Excluded")}


def _ack(screen, seq, **extra):
    now = timezone.now().timestamp() * 1000
    return acks.record(screen, {"seq": seq, "v": "abc", "state": "evacuate", "rendered_at": now,
                                "issued": now - extra.pop("latency", 300), **extra})


def test_p95():
    assert acks.p95([]) is None
    assert acks.p95([5]) == 5
    assert acks.p95(list(range(1, 101))) == 95
    assert acks.p95([100, 1, 50]) == 100


def test_record_latency_and_limits(event, screens):
    a = screens["a"]
    ack = _ack(a, 3, latency=420)
    assert ack.latency_ms == 420 and ack.seq == 3
    assert LatencySample.objects.get(screen_id=a.pk, seq=3).latency_ms == 420
    # the same message again does not add a second sample
    _ack(a, 3, latency=999)
    assert LatencySample.objects.filter(seq=3).count() == 1
    # clock jumps are not latency; rendered before issued is not either
    assert _ack(a, 4, latency=acks.MAX_LATENCY_MS + 1).latency_ms is None
    assert _ack(a, 5, latency=-10).latency_ms is None
    assert acks.record(a, {"seq": -4}).seq == 0
    assert ScreenAck.objects.filter(screen_id=a.pk).count() == 1


def test_coverage_per_zone(event, admin, screens, zones):
    settings_store.save("display", "screen", str(screens["x"].pk), {"evacuation_role": "excluded"})
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    seq = feed.current_seq(event)
    cov = acks.coverage(event)
    assert (cov.total, cov.confirmed, cov.offline, cov.pending) == (4, 0, 2, 2)
    _ack(screens["a"], seq, latency=200)
    _ack(screens["b"], seq - 1)  # an older message does not count
    _ack(screens["c"], seq, latency=1800, fallback=True)  # offline now, but it confirmed the message
    cov = acks.coverage(event)
    assert (cov.total, cov.confirmed, cov.offline, cov.pending, cov.fallback) == (4, 2, 1, 1, 1)
    assert cov.seq == seq and cov.last_p95_ms == 1800 and cov.samples == 3
    by_zone = {z["zone"]: z for z in cov.zones}
    assert by_zone["North"] == {"zone": "North", "total": 2, "confirmed": 2, "offline": 0}
    assert by_zone["South"]["confirmed"] == 0 and by_zone["—"]["offline"] == 1


def test_coverage_without_screens_app(event):
    from django.apps import apps

    with mock.patch.object(apps, "is_installed", return_value=False):
        cov = acks.coverage(event)
    assert cov.total == 0 and cov.p95_ms is None


def test_alarm_since_keeps_the_start_across_stages(event, admin, zones):
    assert acks.alarm_since(event) is None
    services.change(event, "attention", actor=admin, request=tf(admin))
    start = acks.alarm_since(event)
    assert start is not None
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    assert acks.alarm_since(event) == start
    # a zone alarm that started later does not move the start
    services.change(event, "shelter_in_place", zone=zones["South"], actor=admin, request=tf(admin))
    assert acks.alarm_since(event) == start
    services.change(event, "all_clear", actor=admin, request=tf(admin), clear_zones=[str(zones["South"].pk)])
    assert acks.alarm_since(event) is None


def test_staff_ack_audits_alerts_and_emits(event, admin, member, user, zones):
    services.change(event, "evacuate", zone=zones["North"], actor=admin, request=tf(admin), drill=True)
    with mock.patch("apps.core.webhooks.emit") as emit:
        row = acks.staff_ack(event, user, "need_help", zone=zones["North"], note="smoke on stairs")
    assert row.drill and row.seq == feed.current_seq(event) and str(row).endswith("need_help")
    assert AuditLog.objects.filter(action="evacuation.staff_need_help").exists()
    assert emit.call_args.args[0] == "evacuation.staff_ack" and emit.call_args.args[1]["note"] == "smoke on stairs"
    note = Notification.objects.get(user=admin)
    assert "Need help" in note.title and "North" in note.body and "smoke on stairs" in note.body
    acks.staff_ack(event, admin, "on_it")
    assert Notification.objects.count() == 1  # only "need help" alerts
    with pytest.raises(ValueError):
        acks.staff_ack(event, admin, "bogus")
    assert [a.kind for a in acks.recent_staff(event)] == ["on_it", "need_help"]
    assert acks.recent_staff(event, timezone.now() + timedelta(minutes=1)) == []


def test_control_page_shows_coverage(admin_client, event, admin, screens):
    html = admin_client.get(URL).content.decode()
    assert "Screens reached" in html and 'hx-trigger="every 15s"' in html
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    _ack(screens["a"], feed.current_seq(event), latency=3500)
    r = admin_client.get(f"{URL}propagation/")
    html = r.content.decode()
    assert r.status_code == 200 and check_html(html) == []
    assert "1 of 5 screens confirmed" in html and "above the 2000 ms target" in html
    assert 'hx-trigger="every 3s"' in html and "No answers yet" in html
    html = admin_client.get(URL).content.decode()
    assert check_html(html) == [] and "3500 ms" in html


def test_answer_view(admin_client, event, admin, zones):
    url = f"{URL}answer/"
    r = admin_client.post(url, {"kind": "on_it"}, follow=True)
    assert "There is no alarm to answer" in r.content.decode()
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    assert "Unknown answer" in admin_client.post(url, {"kind": "x"}, follow=True).content.decode()
    assert "Unknown zone" in admin_client.post(url, {"kind": "on_it", "zone": "nope"},
                                               follow=True).content.decode()
    r = admin_client.post(url, {"kind": "zone_clear", "zone": str(zones["North"].pk),
                                "next": "https://evil.example/"})
    assert r.status_code == 302 and r["Location"] == URL
    r = admin_client.post(url, {"kind": "on_it", "next": "/e/demo/staff/"})
    assert r["Location"] == "/e/demo/staff/"
    assert StaffAck.objects.count() == 2
    html = admin_client.get(f"{URL}propagation/").content.decode()
    assert "Zone clear" in html and "North" in html


def test_answer_buttons_on_panic_and_staff_pages(admin_client, event, admin):
    assert "Answer the alarm" not in admin_client.get(f"{URL}panic/").content.decode()
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    html = admin_client.get(f"{URL}panic/").content.decode()
    assert "Answer the alarm" in html and check_html(html) == []
    html = admin_client.get("/e/demo/staff/").content.decode()
    assert "I&#x27;m on it" in html or "I'm on it" in html
    assert check_html(html) == []


def test_answer_module_off(admin_client, event):
    from apps.core import modules

    modules.set_event(event, "evacuation", False)
    assert admin_client.post(f"{URL}answer/", {"kind": "on_it"}).status_code == 404
    assert admin_client.get(f"{URL}propagation/").status_code == 404


def test_coverage_api(client, event, admin, screens):
    from apps.accounts.models import ServiceToken

    _t, raw = ServiceToken.issue(name="r", owner=admin, event=event, scopes=["evacuation:read"])
    url = "/api/v1/events/demo/evacuation/coverage/"
    body = client.get(url, HTTP_AUTHORIZATION=f"Bearer {raw}").json()
    assert body["total"] == 5 and body["staff"] == [] and body["p95_ms"] is None
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    _ack(screens["a"], feed.current_seq(event), latency=250)
    acks.staff_ack(event, admin, "on_it")
    body = client.get(url, HTTP_AUTHORIZATION=f"Bearer {raw}").json()
    assert body["confirmed"] == 1 and body["last_p95_ms"] == 250 and body["staff"][0]["kind"] == "on_it"
