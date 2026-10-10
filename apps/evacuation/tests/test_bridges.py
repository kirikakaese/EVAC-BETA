# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hardware bridges: token auth, inputs, contact restored, faults, supervision, HTTPS and MQTT (ADR-0032)."""
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.test import Client
from django.utils import timezone

from apps.core import modules
from apps.core.a11y import check_html
from apps.core.models import AuditLog, Notification
from apps.evacuation import bridges, services, triggers
from apps.evacuation.machine import State
from apps.evacuation.models import Bridge, EvacRequest
from extensions.mqtt import client as mqtt

URL = "/e/demo/evacuation/bridges/"


@pytest.fixture
def bridge(event, admin, zones):
    b, raw = bridges.create(event, "Fire panel", actor=admin)
    bridges.set_inputs(b, bridges.parse_inputs("in1; Relay 3; evacuate; North\nbtn; Button; attention",
                                               {str(z.pk): z.name for z in zones.values()}), actor=admin)
    return b, raw


def post(raw, path, body):
    return Client().post(f"/bridge/v1/{path}", data=json.dumps(body), content_type="application/json",
                         HTTP_AUTHORIZATION=f"Bearer {raw}")


def test_parse_inputs(zones):
    names = {str(z.pk): z.name for z in zones.values()}
    got = bridges.parse_inputs("# comment\n\nin1; Relay; evacuate; north\nk2;Key;staff_alert", names)
    assert got[0]["zone"] == str(zones["North"].pk) and got[1] == {"key": "k2", "label": "Key", "state": "staff_alert",
                                                                   "zone": ""}
    for bad in ("in1; Relay", "in1; R; all_clear", "in1; R; evacuate; Mars", "a; x; evacuate\na; y; evacuate"):
        with pytest.raises(ValueError):
            bridges.parse_inputs(bad, names)


def test_active_input_arms_and_retries_are_harmless(event, bridge, zones):
    b, raw = bridge
    r = post(raw, "input", {"input": "in1", "state": "active", "id": "e1"})
    assert r.status_code == 200 and r.json()["result"] == "armed"
    req = EvacRequest.objects.get()
    assert req.source == "bridge" and req.zone == zones["North"] and "Relay 3" in req.reason
    again = post(raw, "input", {"input": "in1", "state": "active", "id": "e1"})  # the answer got lost: resend
    assert again.json()["result"] == "duplicate" and EvacRequest.objects.count() == 1
    b.refresh_from_db()
    assert b.status["inputs"]["in1"] == "active"


def test_contact_restored_keeps_the_alarm(event, admin, bridge):
    b, raw = bridge
    triggers.save_policy(event, source="bridge", state="", zone=None, action="execute", escalate_seconds=None)
    assert post(raw, "input", {"input": "btn", "state": "active", "id": "a"}).json()["result"] == "executed"
    assert services.effective_for(event, []).state is State.ATTENTION
    assert post(raw, "input", {"input": "btn", "state": "rest", "id": "b"}).json()["result"] == "noted"
    assert services.effective_for(event, []).state is State.ATTENTION  # never auto-clear
    assert Notification.objects.filter(title__startswith="Contact restored").exists()
    assert AuditLog.objects.filter(action="evacuation.bridge_contact_restored").exists()
    # pressing again while the state is active: refused, logged, not an error for the bridge
    post(raw, "input", {"input": "btn", "state": "rest", "id": "c"})
    assert post(raw, "input", {"input": "btn", "state": "active", "id": "d"}).json()["result"] == "refused"


def test_fault_alerts_without_alarm(event, bridge):
    b, raw = bridge
    assert post(raw, "input", {"input": "in1", "state": "fault", "id": "f"}).json()["result"] == "fault_reported"
    post(raw, "input", {"input": "in1", "state": "fault", "id": "g"})
    assert Notification.objects.filter(title__startswith="Input fault").count() == 1  # once per fault (one admin)
    assert services.effective_for(event, []).state is State.NORMAL and not EvacRequest.objects.exists()
    post(raw, "input", {"input": "in1", "state": "rest", "id": "h"})
    assert AuditLog.objects.filter(action="evacuation.bridge_input_ok").exists()


def test_errors(event, bridge):
    b, raw = bridge
    assert post("evacb_wrong", "heartbeat", {}).status_code == 401
    assert post("nope", "heartbeat", {}).status_code == 401
    assert post(raw, "input", {"input": "zz", "state": "active"}).status_code == 404
    assert post(raw, "input", {"input": "in1", "state": "maybe"}).status_code == 400
    r = Client().post("/bridge/v1/heartbeat", data="not json", content_type="application/json",
                      HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert r.status_code == 400
    r = Client().post("/bridge/v1/heartbeat", data="[1]", content_type="application/json",
                      HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert r.status_code == 400
    assert Client().get("/bridge/v1/heartbeat").status_code == 405
    modules.set_event(event, "evacuation", False)
    assert post(raw, "heartbeat", {}).status_code == 409


def test_heartbeat_supervision(event, bridge):
    b, raw = bridge
    r = post(raw, "heartbeat", {"inputs": {"in1": "rest", "btn": "rest"}, "info": {"firmware": "1.0", "x": "y"}})
    body = r.json()
    assert r.status_code == 200 and body["heartbeat_seconds"] == 10 and [i["key"] for i in body["inputs"]] == ["in1",
                                                                                                                "btn"]
    b.refresh_from_db()
    assert b.online and b.status["info"] == {"firmware": "1.0"} and b.last_ip == "127.0.0.1"
    # a change missed earlier arrives with the heartbeat
    post(raw, "heartbeat", {"inputs": {"in1": "active"}})
    assert EvacRequest.objects.filter(source="bridge").count() == 1
    with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(seconds=31)):
        assert triggers.process_due() >= 1
    b.refresh_from_db()
    assert not b.online and Notification.objects.filter(title__startswith="Bridge offline").exists()
    post(raw, "heartbeat", {})
    assert Notification.objects.filter(title__startswith="Bridge back online").exists()


def test_rotate_and_delete(event, admin, bridge):
    b, raw = bridge
    new = bridges.rotate(b, actor=admin)
    assert post(raw, "heartbeat", {}).status_code == 401 and post(new, "heartbeat", {}).status_code == 200
    assert str(b) == "Fire panel"
    bridges.delete(b, actor=admin)
    assert not Bridge.objects.exists()


def test_bridges_page(admin_client, event, zones):
    html = admin_client.get(URL).content.decode()
    assert check_html(html) == [] and "No bridges yet" in html
    r = admin_client.post(URL, {"what": "add", "name": "Panel A"})
    html = r.content.decode()
    assert "shown once" in html and "evacb_" in html
    b = Bridge.objects.get()
    r = admin_client.post(URL, {"what": "inputs", "pk": str(b.pk), "inputs": "in1; Relay; evacuate; North"},
                          follow=True)
    assert "Inputs saved" in r.content.decode()
    b.refresh_from_db()
    assert b.inputs[0]["zone"] == str(zones["North"].pk)
    html = admin_client.get(URL).content.decode()
    assert check_html(html) == [] and "in1; Relay; evacuate; North" in html and "never seen" in html
    r = admin_client.post(URL, {"what": "inputs", "pk": str(b.pk), "inputs": "broken"})
    assert r.status_code == 400 and "Line 1" in r.content.decode()
    assert admin_client.post(URL, {"what": "add", "name": ""}).status_code == 400
    r = admin_client.post(URL, {"what": "rotate", "pk": str(b.pk)})
    assert "shown once" in r.content.decode()
    assert "Unknown bridge" in admin_client.post(URL, {"what": "rotate", "pk": "x"}, follow=True).content.decode()
    admin_client.post(URL, {"what": "delete", "pk": str(b.pk)})
    assert not Bridge.objects.exists()


def test_mqtt_handle(event, bridge):
    b, raw = bridge
    out = mqtt.handle("evac/bridge/abc/heartbeat", json.dumps({"token": raw, "inputs": {"in1": "rest"}}).encode())
    assert out[0] == "evac/bridge/abc/config" and out[1]["name"] == "Fire panel"
    b.refresh_from_db()
    assert b.transport == "mqtt" and b.online
    out = mqtt.handle("site/x/bridge/abc/input", json.dumps({"token": raw, "input": "in1", "state": "active",
                                                             "id": "m1"}).encode(), prefix="site/x")
    assert out == ("site/x/bridge/abc/result", {"id": "m1", "result": "armed"})
    for topic, payload in [("other/bridge/a/input", b"{}"), ("evac/bridge/a/input", b"nope"),
                           ("evac/bridge/a/input", b"[1]"), ("evac/bridge/a/input", b'{"token": "evacb_no"}'),
                           ("evac/bridge/a/other", json.dumps({"token": raw}).encode()), ("evac/bridge/input", b"{}")]:
        assert mqtt.handle(topic, payload) is None


def test_mqtt_config_and_test_connection(event):
    from apps.extensions.models import ExtensionConfig

    assert mqtt.config() is None
    cfg = ExtensionConfig.objects.create(extension="mqtt", enabled=True, settings={"host": "127.0.0.1", "port": 1,
                                                                                    "tls": False, "username": "u"})
    assert mqtt.config() == cfg and mqtt.prefix_of(cfg) == "evac"
    res = mqtt.test_connection(cfg)
    assert not res.ok and res.message
    with mock.patch("paho.mqtt.client.Client.connect", return_value=0), \
            mock.patch("paho.mqtt.client.Client.disconnect"):
        assert mqtt.test_connection(cfg).ok
    cfg.settings = {"host": "127.0.0.1", "tls": True, "topic_prefix": "/x/"}
    with mock.patch("paho.mqtt.client.Client.connect", return_value=5), \
            mock.patch("paho.mqtt.client.Client.disconnect"):
        assert not mqtt.test_connection(cfg).ok
    assert mqtt.prefix_of(cfg) == "x"
