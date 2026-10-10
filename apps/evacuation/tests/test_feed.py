# SPDX-License-Identifier: AGPL-3.0-or-later
"""Screen payloads, the evacuation bundle, signatures, player endpoints and pushes (ADR-0033/0034)."""
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.test import Client
from django.utils import timezone

from apps.core import settings_store
from apps.evacuation import alarmkey, content, feed, services
from apps.evacuation.models import EventAlarm, ScreenAck, StageContent
from apps.screens.models import Screen
from apps.venues.models import Edge, Floor, Point

from .conftest import tf


@pytest.fixture
def screen(event, venue, zones):
    s = Screen.objects.create(event=event, name="Foyer", venue=venue, zone=zones["North"],
                              floor=Floor.objects.get(name="Ground"), position_x=5, position_y=5, facing=180)
    raw = s.issue_token()
    s.save()
    return s, raw


@pytest.fixture
def plan(venue):
    ground = Floor.objects.get(name="Ground")
    w1 = Point.objects.create(venue=venue, floor=ground, name="W1", kind="waypoint", x=0, y=0)
    ex = Point.objects.create(venue=venue, floor=ground, name="East", kind="exit", x=40, y=0)
    a = Point.objects.create(venue=venue, floor=None, name="Meadow", kind="assembly", x=0, y=-30)
    Edge.objects.create(venue=venue, a=w1, b=ex)
    Edge.objects.create(venue=venue, a=w1, b=a)
    return {"w1": w1, "ex": ex, "a": a}


def api(raw):
    return {"HTTP_AUTHORIZATION": f"Screen {raw}"}


def test_payload_and_bundle(event, admin, screen, plan, zones):
    s, raw = screen
    services.change(event, "evacuate", zone=zones["North"], actor=admin, request=tf(admin), drill=True)
    body = feed.payloads(event)[str(s.pk)]
    assert body["state"] == "evacuate" and body["drill"] and body["takeover"] and body["role"] == "participant"
    assert body["guidance"]["kind"] == "route" and body["direction"] == "Meadow" and body["guidance"]["arrow"]
    assert body["texts"] == feed.DEFAULT_TEXTS["evacuate"] and body["sound"] == "siren" and body["layout"] is None
    assert body["seq"] == feed.current_seq(event) >= 1 and len(body["v"]) == 16
    b = feed.bundle(s)
    assert set(b["stages"]) == {"attention", "shelter_in_place", "evacuate", "all_clear"}
    assert b["zones"] == [str(zones["North"].pk)] and b["keys"] == alarmkey.public_keys(event)
    # a direction for the live situation and one per blocked exit or assembly point
    assert "" in b["directions"] and str(plan["a"].pk) in b["directions"]
    assert b["directions"][str(plan["a"].pk)]["target"] == "East"
    settings_store.save("evacuation", "event", str(event.pk), {"model": "staged",
                                                               "fallback_origins": ["http://10.0.0.5:8088/"]},
                        event=event)
    b = feed.bundle(s)
    assert list(b["directions"]) == [""] and b["fallback_origins"] == ["http://10.0.0.5:8088"]


def test_signatures_and_rotation(event, admin):
    row = alarmkey.ensure(event)
    assert row.public_key and alarmkey.ensure(event).public_key == row.public_key
    signed = alarmkey.sign_payload(event, {"event": "demo", "screen": "s", "seq": 3, "state": "evacuate",
                                           "drill": False, "takeover": True, "v": "abc"})
    core = alarmkey.verify(alarmkey.public_keys(event), signed["sig"])
    assert core["st"] == "evacuate" and core["seq"] == 3
    tampered = {**signed["sig"], "m": signed["sig"]["m"].replace("evacuate", "normal")}
    assert alarmkey.verify(alarmkey.public_keys(event), tampered) is None
    old = row.public_key
    alarmkey.rotate(event, actor=admin)
    keys = alarmkey.public_keys(event)
    assert keys[1] == old and alarmkey.verify(keys, signed["sig"]) is not None  # grace period
    with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(days=2)):
        assert alarmkey.public_keys(event) == keys[:1]
    raw = alarmkey.export_private(event, actor=admin, purpose="bridge hall A")
    assert len(alarmkey.unb64(raw)) == 32
    from apps.core.models import AuditLog

    assert AuditLog.objects.filter(action="evacuation.alarm_key_exported").exists()
    assert str(EventAlarm.objects.get(event=event)).startswith("alarm #")


def test_state_message(event, admin, zones):
    services.change(event, "attention", actor=admin, request=tf(admin))
    services.change(event, "evacuate", zone=zones["North"], actor=admin, request=tf(admin))
    services.change(event, "all_clear", zone=zones["North"], actor=admin, request=tf(admin))
    msg = alarmkey.state_message(event)
    core = alarmkey.verify(alarmkey.public_keys(event), msg["sig"])
    assert core["ev"] == {"st": "attention", "d": False} and core["z"][str(zones["North"].pk)]["st"] == "all_clear"
    assert core["z"][str(zones["North"].pk)]["cu"] > 0 and core["b"] == []
    r = Client().get("/evac/demo/state")
    assert r.status_code == 200 and r["Access-Control-Allow-Origin"] == "*" and "sig" in r.json()
    assert Client().get("/evac/nope/state").status_code == 404


def test_player_state_and_ack(event, admin, screen, zones):
    s, raw = screen
    c = Client()
    assert c.get("/player/api/evacuation/state/").status_code == 401
    body = c.get("/player/api/evacuation/state/", **api(raw)).json()
    assert body["enabled"] and body["payload"]["state"] == "normal" and "sig" in body["payload"]
    assert body["bundle"]["event"] == "demo"
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    p = c.get("/player/api/evacuation/state/", **api(raw)).json()["payload"]
    now_ms = int(timezone.now().timestamp() * 1000)
    r = c.post("/player/api/evacuation/ack/", json.dumps({"seq": p["seq"], "v": p["v"], "state": "evacuate",
                                                          "rendered_at": now_ms + 400, "issued": now_ms,
                                                          "via": "websocket", "fallback": True}),
               content_type="application/json", **api(raw))
    assert r.status_code == 200
    ack = ScreenAck.objects.get(screen_id=s.pk)
    assert ack.latency_ms == 400 and ack.fallback and ack.seq == p["seq"] and str(ack).endswith(f"#{p['seq']}")
    for bad in (b"nope", b"[1]"):
        assert c.post("/player/api/evacuation/ack/", bad, content_type="application/json",
                      **api(raw)).status_code == 400
    assert c.post("/player/api/evacuation/ack/", b"{}", content_type="application/json").status_code == 401
    # nonsense values are stored without a latency
    c.post("/player/api/evacuation/ack/", json.dumps({"seq": "x", "rendered_at": "y", "issued": "z"}),
           content_type="application/json", **api(raw))
    assert ScreenAck.objects.get(screen_id=s.pk).latency_ms is None
    from apps.core import modules

    modules.set_event(event, "evacuation", False)
    assert c.get("/player/api/evacuation/state/", **api(raw)).json() == {"enabled": False}


def test_push_sends_every_screen_its_payload(event, admin, screen, django_capture_on_commit_callbacks):
    s, raw = screen
    with mock.patch("apps.screens.channel.send") as send, django_capture_on_commit_callbacks(execute=True):
        services.change(event, "shelter_in_place", actor=admin, request=tf(admin))
    sent = [c for c in send.call_args_list if c.args[1] == "evac.state"]
    assert len(sent) == 1
    body = sent[0].args[2]
    assert body["state"] == "shelter_in_place" and body["issued"] > 0 and "sig" in body
    # settings that shape payloads push too; changes in one transaction send once (the newest wins)
    with mock.patch("apps.screens.channel.send") as send, django_capture_on_commit_callbacks(execute=True):
        settings_store.save("evacuation_screen", "screen", str(s.pk), {"hint_text": "Exit B"})
        settings_store.save("evacuation", "instance", "", {"model": "zones", "drill_text": "EXERCISE"})
    pushed = [c.args[2] for c in send.call_args_list if c.args[1] == "evac.state"]
    assert len(pushed) == 1 and pushed[0]["drill_text"] == "EXERCISE" and pushed[0]["direction"] == "Exit B"
    with mock.patch("apps.screens.channel.send") as send:
        for value in ("A", "B"):
            with django_capture_on_commit_callbacks(execute=True):
                settings_store.save("evacuation_screen", "screen", str(s.pk), {"hint_text": value})
    assert [c.args[2]["direction"] for c in send.call_args_list if c.args[1] == "evac.state"] == ["A", "B"]
    with mock.patch("django.apps.apps.is_installed", return_value=False), \
            mock.patch("apps.screens.channel.send") as send, django_capture_on_commit_callbacks(execute=True):
        feed.push(event)
    assert not send.called


def test_roles(event, admin, screen):
    s, raw = screen
    settings_store.save("display", "screen", str(s.pk), {"evacuation_role": "excluded"})
    assert feed.payloads(event)[str(s.pk)]["role"] == "excluded"
    with mock.patch("apps.screens.display.for_screen", side_effect=RuntimeError):
        assert feed._role(s) == "participant"


def test_speech_url_and_endpoint(event, screen, tmp_path, settings):
    s, raw = screen
    assert feed.speech_url("", s) == ""
    url = feed.speech_url("abc.wav", s)
    c = Client()
    with mock.patch("apps.announcements.tts.path_of", return_value=tmp_path / "abc.wav"):
        assert c.get(url).status_code == 404  # not rendered
        (tmp_path / "abc.wav").write_bytes(b"RIFF")
        r = c.get(url)
        assert r.status_code == 200 and r["Content-Type"] == "audio/wav"
    assert c.get(url.replace("abc.wav", "x.wav")).status_code == 404
    assert c.get("/player/api/evacuation/speech/abc.wav?s=bad").status_code == 404
    with mock.patch("django.apps.apps.is_installed", return_value=False):
        assert c.get(url).status_code == 404


def test_stage_content_and_speech_job(event, admin):
    with mock.patch("apps.evacuation.content.tts_available", return_value=True), \
            mock.patch("apps.core.outbox.enqueue") as enqueue:
        row = content.save(event, "evacuate", layout=None, texts=["Raus hier", " ", "Go"], rotate_seconds=1,
                           pictograms_only=True, sound="gong", sound_every=2, speech_text="Leave now", actor=admin)
    assert row.texts == ["Raus hier", "Go"] and row.rotate_seconds == 3 and row.sound_every == 5
    assert row.speech_status == "pending" and enqueue.called and str(row) == "evacuate content"
    job = mock.Mock(payload={"content": str(row.pk)})
    with mock.patch("apps.announcements.tts.render", return_value="x.wav"):
        content.render_speech(job)
    row.refresh_from_db()
    assert row.speech_status == "ready" and row.speech_file == "x.wav"
    assert feed.stage_content(event, "evacuate")["speech"] == "x.wav"
    from apps.announcements import tts

    with mock.patch("apps.announcements.tts.render", side_effect=tts.SpeechError("no voice")):
        content.render_speech(job)
    row.refresh_from_db()
    assert row.speech_status == "failed" and "no voice" in row.speech_detail
    job = mock.Mock(payload={"content": "00000000-0000-0000-0000-000000000000"})
    content.render_speech(job)
    assert job.result == {"skipped": True}
    with mock.patch("django.apps.apps.is_installed", return_value=False):
        content.render_speech(mock.Mock(payload={"content": str(row.pk)}))
        assert not content.tts_available() and content.layouts_of(event) == []
        assert feed.layout_data("00000000-0000-0000-0000-000000000000") is None
    assert StageContent.objects.count() == 1
