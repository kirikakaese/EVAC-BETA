# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-safe (roadmap 3.9, ADR-0034): watchdog, readiness, self-test, alarm key, bridge-issued alarms."""
import importlib.util
import json
import pathlib
import sys
from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone

from apps.core.a11y import check_html
from apps.core.models import AuditLog, Notification
from apps.evacuation import acks, alarmkey, bridges, feed, readiness, services
from apps.evacuation.models import EventAlarm, ScreenAck, StateChange
from apps.screens.models import Screen
from conftest import login_2fa

from .conftest import tf

URL = "/e/demo/evacuation/readiness/"


def _screen(event, name, health="online", **reported):
    s = Screen.objects.create(event=event, name=name)
    raw = s.issue_token()
    s.health_state = health
    s.reported = reported
    s.save()
    return s, raw


def _bridge_module():
    path = pathlib.Path(__file__).parents[3] / "bridge" / "evac_bridge.py"
    spec = importlib.util.spec_from_file_location("evac_bridge", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["evac_bridge"] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------- watchdog
def test_watchdog_alerts_once_per_message(event, admin):
    a, _ra = _screen(event, "A")
    b, _rb = _screen(event, "B", health="offline")
    assert acks.watchdog(event) == 0
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    row = EventAlarm.objects.get(event=event)
    assert row.seq_at is not None
    assert acks.watchdog(event) == 0  # too early
    later = timezone.now() + timedelta(seconds=acks.WATCHDOG_SECONDS + 1)
    acks.record(a, {"seq": row.seq})
    assert acks.watchdog(event, later) == 1
    note = Notification.objects.get(user=admin)
    assert "1 of 2 screens" in note.title and "B (offline)" in note.body
    assert acks.watchdog(event, later) == 0  # once per message
    assert AuditLog.objects.filter(action="evacuation.watchdog").count() == 1
    # every screen confirmed: no alert, but the message is done
    services.change(event, "shelter_in_place", actor=admin, request=tf(admin))
    seq = feed.current_seq(event)
    acks.record(a, {"seq": seq})
    acks.record(b, {"seq": seq})
    assert acks.watchdog(None, later + timedelta(minutes=1)) == 0
    assert EventAlarm.objects.get(event=event).watchdog_seq == seq
    # outside an alarm nothing is watched
    services.change(event, "all_clear", actor=admin, request=tf(admin))
    assert acks.watchdog(event, later + timedelta(minutes=2)) == 0


def test_process_due_runs_the_watchdog(event, admin):
    from apps.evacuation import triggers

    _screen(event, "A")
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    EventAlarm.objects.filter(event=event).update(seq_at=timezone.now() - timedelta(minutes=1))
    assert triggers.process_due() >= 1
    assert Notification.objects.filter(title__contains="did not confirm").exists()


# ------------------------------------------------------------------------------------------- player endpoints
def test_state_records_bundle_and_selftest_endpoint(event):
    s, raw = _screen(event, "A")
    c = Client()
    auth = {"HTTP_AUTHORIZATION": f"Screen {raw}"}
    body = c.get("/player/api/evacuation/state/", **auth).json()
    ack = ScreenAck.objects.get(screen_id=s.pk)
    assert ack.bundle_served == body["bundle"]["version"] and ack.bundle_served_at
    result = {"ok": False, "bundle": "x" * 40, "keys": 1, "signature": "ok", "audio": "suspended",
              "stages": {"evacuate": "ok", "attention": "fallback (t1: boom)"},
              "origins": {"https://bridge": "unreachable"}, "visible": True, "ms": 42, "junk": "x"}
    r = c.post("/player/api/evacuation/selftest/", json.dumps(result), content_type="application/json", **auth)
    assert r.status_code == 200
    ack.refresh_from_db()
    assert ack.selftest["ms"] == 42 and ack.selftest["bundle"] == "x" * 16 and "junk" not in ack.selftest
    assert ack.selftest["origins"] == {"https://bridge": "unreachable"} and ack.selftest_at
    for bad in (b"nope", b"[1]"):
        assert c.post("/player/api/evacuation/selftest/", bad, content_type="application/json",
                      **auth).status_code == 400
    assert c.post("/player/api/evacuation/selftest/", b"{}", content_type="application/json").status_code == 401
    acks.record_selftest(s, {"keys": "x", "stages": "nope", "ms": "1"})
    ack.refresh_from_db()
    assert ack.selftest["keys"] == 0 and ack.selftest["stages"] == {} and ack.selftest["ms"] is None


# ------------------------------------------------------------------------------------------- readiness
def test_readiness_rows(event):
    now = timezone.now()
    ok, _r = _screen(event, "OK", evac_bundle="v1", evac_audio="running")
    stale, _r = _screen(event, "Stale", evac_bundle="old", evac_audio="suspended")
    off, _r = _screen(event, "Off", health="offline", evac_audio="unavailable")
    excluded, _r = _screen(event, "Excluded", health="offline")
    for s, v in ((ok, "v1"), (stale, "v2")):
        ScreenAck.objects.create(screen_id=s.pk, event=event, bundle_served=v,
                                 bundle_served_at=now - timedelta(minutes=15), selftest_at=now - timedelta(days=1),
                                 selftest={"ok": s is ok, "stages": {"evacuate": "error: x"},
                                           "signature": "invalid", "origins": {"o": "unreachable"}})
    with mock.patch.object(feed, "_role", side_effect=lambda s: "excluded" if s.name == "Excluded" else "participant"):
        rows = {r.screen.name: r for r in readiness.screens(event, now)}
        summary = readiness.summary(list(rows.values()))
    assert rows["OK"].ready and rows["OK"].warnings == ["bundle not refreshed for 15 minutes"]
    st = rows["Stale"]
    assert "evacuation bundle not current" in st.problems and "sound blocked by the browser (autoplay)" in st.problems
    assert any("evacuate: error: x" in p and "signature does not verify" in p and "o: unreachable" in p
               for p in st.problems)
    off_row = rows["Off"]
    assert "offline" in off_row.problems and "has not loaded the evacuation bundle" in off_row.problems
    assert "no sound output" in off_row.warnings and "never self-tested" in off_row.warnings
    assert rows["Excluded"].problems == []
    assert summary == {"total": 3, "ready": 1, "problems": 2, "warnings": 3}
    ScreenAck.objects.filter(screen_id=ok.pk).update(selftest_at=now - timedelta(days=8), selftest={})
    Screen.objects.filter(pk=ok.pk).update(health_state="stale")
    row = next(r for r in readiness.screens(event, now) if r.screen.name == "OK")
    assert "last self-test over 7 days ago" in row.warnings and "self-test: failed" in row.problems
    assert "no recent heartbeat" in row.problems


def test_readiness_page_and_selftest(admin_client, event, admin):
    s, _r = _screen(event, "A")
    r = admin_client.get(URL)
    html = r.content.decode()
    assert r.status_code == 200 and check_html(html) == [] and "0 of 1 screens ready" in html
    with mock.patch("apps.screens.channel.send") as send:
        r = admin_client.post(URL, {"what": "selftest", "visible": "on", "seconds": "99"}, follow=True)
    assert "Self-test sent to 1 screens" in r.content.decode()
    assert send.call_args.args[1:] == ("evac.selftest", {"visible": True, "seconds": 60})
    assert AuditLog.objects.filter(action="evacuation.selftest").exists()
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    with mock.patch("apps.screens.channel.send") as send:
        r = admin_client.post(URL, {"what": "selftest", "visible": "on"}, follow=True)
    assert "No visible self-test during an alarm" in r.content.decode() and not send.called
    assert admin_client.get("/e/demo/evacuation/").content.decode().count("readiness/") >= 1


def test_alarm_key_rotate_and_export(admin_client, client, event, admin, member):
    before = alarmkey.public_keys(event)[0]
    with mock.patch.object(feed, "push") as push:
        admin_client.post(URL, {"what": "rotate"})
    keys = alarmkey.public_keys(event)
    assert keys[0] != before and keys[1] == before and push.called
    r = admin_client.post(URL, {"what": "export", "purpose": "bridge hall A"})
    html = r.content.decode()
    raw = alarmkey.export_private(event)
    assert raw in html and "shown once" in html and check_html(html) == []
    assert AuditLog.objects.filter(action="evacuation.alarm_key_exported", message__contains="bridge hall A").exists()
    # without two factors in this session: refused
    session = admin_client.session
    from apps.accounts.twofactor import SESSION_KEY

    del session[SESSION_KEY]
    session.save()
    r = admin_client.post(URL, {"what": "export"}, follow=True)
    assert "two factors" in r.content.decode() and raw not in r.content.decode()
    # people without evacuation.manage can look but not act
    login_2fa(client, member)
    assert client.get(URL).status_code == 200
    assert client.post(URL, {"what": "selftest"}).status_code == 403


def test_management_commands(event, admin):
    s, _r = _screen(event, "A")
    out = StringIO()
    call_command("evac_alarm_key", "demo", "show", stdout=out)
    assert out.getvalue().startswith("current ")
    out = StringIO()
    call_command("evac_alarm_key", "demo", "export", "--purpose", "node", stdout=out)
    assert out.getvalue().strip() == alarmkey.export_private(event)
    call_command("evac_alarm_key", "demo", "rotate", stdout=StringIO())
    assert len(alarmkey.public_keys(event)) == 2
    with pytest.raises(CommandError):
        call_command("evac_alarm_key", "nope", "show")
    with mock.patch("apps.screens.channel.send"):
        out = StringIO()
        call_command("evac_selftest", "demo", stdout=out)
    assert "sent to 1 screens" in out.getvalue()
    out = StringIO()
    with pytest.raises(SystemExit):
        call_command("evac_selftest", "demo", "--report", stdout=out)
    assert "PROBLEM  A" in out.getvalue() and "0 of 1 ready" in out.getvalue()
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    with pytest.raises(CommandError):
        call_command("evac_selftest", "demo", "--visible")
    with pytest.raises(CommandError):
        call_command("evac_selftest", "nope")
    ScreenAck.objects.update_or_create(screen_id=s.pk, defaults={
        "event": event, "bundle_served": "v", "bundle_served_at": timezone.now(), "selftest_at": timezone.now(),
        "selftest": {"ok": True}})
    Screen.objects.filter(pk=s.pk).update(reported={"evac_bundle": "v", "evac_audio": "running"})
    out = StringIO()
    call_command("evac_selftest", "demo", "--report", stdout=out)
    assert "ready    A" in out.getvalue()


# ------------------------------------------------------------------------------------------- bridges
@pytest.fixture
def bridge(event, admin, zones):
    b, raw = bridges.create(event, "Fire panel", actor=admin)
    bridges.set_inputs(b, bridges.parse_inputs("in1; Relay 3; evacuate; North\nbtn; Button; attention",
                                               {str(z.pk): z.name for z in zones.values()}), actor=admin)
    return b, raw


def test_heartbeat_hands_out_state_and_policies(event, bridge, zones):
    b, _raw = bridge
    cfg = bridges.heartbeat(b, inputs={})
    assert cfg["inputs"][0]["zone"] == str(zones["North"].pk)
    assert cfg["inputs"][0]["policy"] == {"action": "arm", "escalate_seconds": 120}
    core = alarmkey.verify(cfg["keys"], cfg["state"]["sig"])
    assert core["e"] == "demo" and core["seq"] == feed.current_seq(event)


def test_bridge_issued_alarm_is_adopted(event, admin, bridge, zones):
    b, raw = bridge
    eb = _bridge_module()
    services.change(event, "attention", actor=admin, request=tf(admin))
    cfg = bridges.heartbeat(b, inputs={})
    # the server becomes unreachable; the fire panel relay closes; the bridge signs the alarm itself
    fb = eb.FallbackState(None, key=alarmkey.export_private(event), name="panel")
    fb.update(cfg)
    issued = fb.issue("in1")
    assert issued == feed.current_seq(event) + 1
    core = alarmkey.verify(alarmkey.public_keys(event), fb.message["sig"])
    assert core["is"] == "bridge:panel" and core["z"][str(zones["North"].pk)]["st"] == "evacuate"
    # back online: the queued change carries issued_seq; the server executes (no arming) and moves seq past it
    r = Client().post("/bridge/v1/input", data=json.dumps({"input": "in1", "state": "active", "id": "c1",
                                                           "issued_seq": issued}),
                      content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert r.status_code == 200 and r.json()["result"] == "executed"
    assert services.statuses(event)[1][str(zones["North"].pk)].state.value == "evacuate"
    assert feed.current_seq(event) > issued
    change = StateChange.objects.filter(zone=zones["North"]).latest("at")
    assert change.source == "bridge" and "issued by the bridge" in change.reason
    assert AuditLog.objects.filter(action="evacuation.bridge_issued").exists()
    assert Notification.objects.filter(title__contains="on its own").exists()


def test_adopt_seq_limits(event):
    feed.bump(event)
    assert not bridges.adopt_seq(event, 1)  # not ahead
    assert not bridges.adopt_seq(event, 1 + bridges.MAX_SEQ_JUMP + 1)  # implausible
    assert bridges.adopt_seq(event, 50) and feed.current_seq(event) == 50
