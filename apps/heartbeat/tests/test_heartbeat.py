# SPDX-License-Identifier: AGPL-3.0-or-later
"""Heartbeat (ADR-0052): the health check registry, every built-in check, status changes with grace and without
flapping, alerts and webhooks, recovery, operator check-in with escalation, permissions, the module switch and the
alive indicator widget."""
import datetime as dt

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core import modules, settings_store
from apps.core.a11y import audit_url
from apps.core.models import AuditLog, Notification, OutboxJob
from apps.core.plugins import API_VERSION, HealthCheckSpec, HealthItem, NotificationChannelSpec
from apps.core.registry import Registry, RegistryError, registry
from apps.events import services as ev
from apps.events.models import Event
from apps.heartbeat import checkin, checks, services, tasks
from apps.heartbeat.models import CheckIn, CheckInEscalation, HealthState, Pulse
from conftest import login_2fa

T0 = dt.datetime(2026, 7, 1, 12, 0, tzinfo=dt.UTC)


def live(event, state="live"):
    Event.objects.filter(pk=event.pk).update(state=state)
    event.refresh_from_db()
    return event


@pytest.fixture
def control(event, role):
    u = User.objects.create_user(email="control@example.org", password="pw-control-123", display_name="Control")
    ev.assign_role(event, u, role("control-room"))
    return u


@pytest.fixture
def orga_user(event, role):
    u = User.objects.create_user(email="orga2@example.org", password="pw-orga2-12345", display_name="Orga")
    ev.assign_role(event, u, role("orga"))
    return u


@pytest.fixture
def hooks():
    """Captures emitted webhook events."""
    seen = []
    sinks = registry.ensure_loaded().webhook_sinks

    def sink(kind, payload, event):
        seen.append((kind, payload))
    sinks.append(sink)
    yield seen
    sinks.remove(sink)


@pytest.fixture
def channel():
    sent = []
    reg = registry.ensure_loaded().notification_channels
    reg["fake"] = NotificationChannelSpec(key="fake", name="Fake", alert=lambda e, a: sent.append(a) or {})
    yield sent
    del reg["fake"]


class Fake:
    """A health check whose items the test sets."""

    def __init__(self):
        self.items = [HealthItem(key="a", label="Thing A", status="ok")]

    def __call__(self, event):
        return self.items

    def set(self, *statuses):
        self.items = [HealthItem(key=f"k{i}", label=f"Thing {i}", status=s, detail=f"detail {i}")
                      for i, s in enumerate(statuses)]


@pytest.fixture
def fake():
    f = Fake()
    checks_ = registry.ensure_loaded().health_checks
    checks_["fake"] = HealthCheckSpec(key="fake", name="Fake", check=f, scope="both")
    yield f
    del checks_["fake"]


# ------------------------------------------------------------------ registry
def test_registry_hook_and_api_version():
    assert API_VERSION == 6
    keys = set(registry.ensure_loaded().health_checks)
    assert {"screens", "nodes.event", "nodes.instance", "evacuation.bridges", "dial", "celery", "outbox",
            "extensions", "widgets.feeds"} <= keys
    r = Registry()
    spec = HealthCheckSpec(key="x", name="X", check=lambda e: [])
    r.health_check(spec)
    with pytest.raises(RegistryError):
        r.health_check(spec)


def test_specs_skip_disabled_modules_scope_and_checkout(event, monkeypatch):
    keys = [s.key for s in services.specs_for(event)]
    assert "screens" in keys and "outbox" in keys and "celery" in keys
    assert "evacuation.bridges" not in keys  # evacuation is off by default
    assert "nodes.instance" not in keys  # instance scope only
    modules.set_event(event, "screens", False)
    assert "screens" not in [s.key for s in services.specs_for(event)]
    modules.set_instance("evacuation", True)
    assert "evacuation.bridges" in [s.key for s in services.specs_for(event)]
    inst = [s.key for s in services.specs_for(None)]
    assert "nodes.instance" in inst and "screens" not in inst and "outbox" in inst
    from apps.nodes import guard

    monkeypatch.setattr(guard, "remote", lambda e: True)
    remote = [s.key for s in services.specs_for(event)]
    assert "nodes.event" in remote and "outbox" in remote and "evacuation.bridges" not in remote


def test_broken_check_and_plain_dicts(event):
    reg = registry.ensure_loaded().health_checks

    def broken(e):
        raise RuntimeError("boom")
    reg["broken"] = HealthCheckSpec(key="broken", name="Broken", check=broken)
    reg["dicts"] = HealthCheckSpec(key="dicts", name="Dicts", check=lambda e: [
        {"key": "d", "label": "D", "status": "weird", "detail": "x"}, {"status": "down"}])
    try:
        obs = {(o.spec.key, o.item.key): o.item for o in services.observe(event)}
    finally:
        del reg["broken"], reg["dicts"]
    assert obs[("broken", "broken")].status == "unknown" and "RuntimeError" in obs[("broken", "broken")].detail
    assert obs[("dicts", "d")].status == "unknown"
    assert obs[("dicts", "dicts")].status == "down" and obs[("dicts", "dicts")].label == "Dicts"
    with pytest.raises(TypeError):
        services.normalise(42, reg["screens"])


# ------------------------------------------------------------------ the checks
def test_screens_check(event):
    from apps.screens import health
    from apps.screens.models import Screen

    now = timezone.now()
    Screen.objects.create(event=event, name="Never", token_hash="a" * 64)
    Screen.objects.create(event=event, name="Live", token_hash="b" * 64, last_seen_at=now)
    Screen.objects.create(event=event, name="Gone", token_hash="c" * 64, last_seen_at=now - dt.timedelta(hours=1))
    Screen.objects.create(event=event, name="Unpaired")
    items = {i.label: i for i in health.check(event)}
    assert set(items) == {"Never", "Live", "Gone"}
    assert (items["Never"].status, items["Live"].status, items["Gone"].status) == ("unknown", "ok", "down")
    assert "No heartbeat" in items["Gone"].detail and items["Live"].url.startswith("/e/demo/screens/")


def test_node_checks(event, settings):
    from apps.nodes import health
    from apps.nodes.models import Checkout, Node, NodeIdentity

    now = timezone.now()
    node = Node.objects.create(name="Hall node", enrolled_at=now, last_seen=now)
    idle = Node.objects.create(name="Spare", enrolled_at=now, last_seen=now - dt.timedelta(days=2))
    assert health.event_check(event) == []
    Checkout.objects.create(event=event, node=node, last_sync=now)
    [item] = health.event_check(event)
    assert item.status == "ok" and "Hall node" in item.label
    Node.objects.filter(pk=node.pk).update(last_seen=now - dt.timedelta(minutes=3))
    assert health.event_check(event)[0].status == "warn"
    Node.objects.filter(pk=node.pk).update(last_seen=now - dt.timedelta(minutes=10))
    assert health.event_check(event)[0].status == "down"
    inst = {i.key: i for i in health.instance_check(None)}
    assert inst[str(node.pk)].status == "down" and inst[str(idle.pk)].status == "unknown"
    assert "No event checked out" in inst[str(idle.pk)].detail
    settings.EVAC_MODE = "node"
    assert health.event_check(event) == [] and health.instance_check(None) == []
    NodeIdentity.objects.create(pk=1, enrolled_at=now, last_contact=now - dt.timedelta(minutes=30),
                                last_error="timeout")
    [link] = health.instance_check(None)
    assert link.status == "warn" and "timeout" in link.detail  # a venue works offline: never "down"


def test_bridge_check(event):
    from apps.evacuation import health
    from apps.evacuation.models import Bridge

    now = timezone.now()
    b = Bridge.objects.create(event=event, name="Panel relay", token_hash="h1", token_prefix="p1")
    assert health.check(event)[0].status == "unknown"
    Bridge.objects.filter(pk=b.pk).update(last_seen=now, online=True)
    assert health.check(event)[0].status == "ok"
    Bridge.objects.filter(pk=b.pk).update(status={"inputs": {"in1": "fault"}})
    item = health.check(event)[0]
    assert item.status == "warn" and "in1" in item.detail
    Bridge.objects.filter(pk=b.pk).update(last_seen=now - dt.timedelta(minutes=2))
    item = health.check(event)[0]
    assert item.status == "down" and "cannot raise alarms" in item.detail
    b.refresh_from_db()
    assert b.online  # read-only: the bridge supervision decides, not the heartbeat


def test_dial_and_extensions_checks(event):
    from apps.extensions import health as ext_health
    from apps.extensions.models import ExtensionConfig
    from extensions.dial import health
    from extensions.dial.models import Broadcast, Snapshot

    assert health.check(event) == []
    cfg = ExtensionConfig.objects.create(extension="dial", event=event, enabled=True)
    assert health.check(event)[0].status == "unknown"
    ExtensionConfig.objects.filter(pk=cfg.pk).update(health="error", last_error="401 Unauthorized")
    item = health.check(event)[0]
    assert item.status == "down" and "401" in item.detail
    ExtensionConfig.objects.filter(pk=cfg.pk).update(health="ok", last_error="")
    assert health.check(event)[0].status == "ok"
    Snapshot.objects.create(config=cfg, key="dect", error="timeout", fetched_at=timezone.now())
    Broadcast.objects.create(config=cfg, event=event, kind="message", source="test", text="x", status="failed")
    item = health.check(event)[0]
    assert item.status == "warn" and "timeout" in item.detail and "1 broadcasts" in item.detail
    # the generic extensions check leaves DIAL to its own check
    assert all(i.key != "dial" for i in ext_health.check(event))
    other = ExtensionConfig.objects.create(extension="pretix", event=event, enabled=True, health="error",
                                           last_error="bad token")
    items = {i.key: i for i in ext_health.check(event)}
    assert items["pretix"].status == "warn" and "bad token" in items["pretix"].detail
    ExtensionConfig.objects.filter(pk=other.pk).update(health="ok")
    assert {i.key: i for i in ext_health.check(event)}["pretix"].status == "ok"


def test_outbox_check(event):
    from apps.core import health

    assert health.outbox(event)[0].status == "ok"
    job = OutboxJob.objects.create(kind="x", event=event, idempotency_key="k1", payload={})
    assert health.outbox(event)[0].status == "ok"
    OutboxJob.objects.filter(pk=job.pk).update(created_at=timezone.now() - dt.timedelta(minutes=5))
    item = health.outbox(event)[0]
    assert item.status == "warn" and "1 waiting" in item.detail
    OutboxJob.objects.filter(pk=job.pk).update(created_at=timezone.now() - dt.timedelta(minutes=20))
    assert health.outbox(event)[0].status == "down"
    assert health.outbox(None)[0].status == "down"
    OutboxJob.objects.filter(pk=job.pk).update(status="dead")
    item = health.outbox(event)[0]
    assert item.status == "warn" and "gave up" in item.detail


def test_feeds_check(event):
    from apps.widgets import health
    from apps.widgets.models import Feed

    Feed.objects.create(event=event, name="Weather", url="https://example.org/w.json", status="ok",
                        last_success_at=timezone.now())
    Feed.objects.create(event=event, name="Trains", url="https://example.org/t.json", status="error",
                        error="HTTP 500")
    items = {i.label: i for i in health.check(event)}
    assert items["Weather"].status == "ok" and items["Trains"].status == "warn" and "HTTP 500" in items[
        "Trains"].detail


def test_celery_check(event):
    assert checks.celery(event)[0].status == "unknown"
    checks.beat()
    assert checks.celery(event)[0].status == "ok"
    Pulse.objects.update(at=timezone.now() - dt.timedelta(minutes=5))
    assert checks.celery(event)[0].status == "warn"
    Pulse.objects.update(at=timezone.now() - dt.timedelta(minutes=20))
    assert checks.celery(None)[0].status == "down"


# ------------------------------------------------------------------ status changes
def test_grace_no_flapping_alert_and_recovery(event, fake, control, hooks, channel,
                                              django_capture_on_commit_callbacks):
    from apps.ops.models import LogEntry

    live(event)
    settings_store.save("heartbeat", "event", str(event.pk), {"alert_channels": ["fake", "nope"]})
    fake.set("ok")
    with django_capture_on_commit_callbacks(execute=True):
        assert services.evaluate(event, T0) == []
        fake.set("down")
        assert services.evaluate(event, T0 + dt.timedelta(seconds=10)) == []  # a blip so far
        fake.set("ok")
        assert services.evaluate(event, T0 + dt.timedelta(seconds=20)) == []  # back: no alert, no flapping
        fake.set("down")
        assert services.evaluate(event, T0 + dt.timedelta(seconds=30)) == []
        assert services.evaluate(event, T0 + dt.timedelta(seconds=80)) == []  # 50 s < 60 s grace
        [change] = services.evaluate(event, T0 + dt.timedelta(seconds=91))
    assert (change.old, change.new) == ("ok", "down")
    st = HealthState.objects.get(event=event, check_key="fake", item="k0")
    assert st.status == "down" and st.alerted and st.since == T0 + dt.timedelta(seconds=30)
    note = Notification.objects.get(user=control)
    assert note.title == "Down: Fake: Thing 0" and note.level == "err" and note.url == "/e/demo/heartbeat/"
    job = OutboxJob.objects.get(kind="core.alert")
    assert job.payload["channel"] == "fake" and job.payload["title"] == "Down: Fake: Thing 0"
    assert [k for k, _p in hooks] == ["heartbeat.down"] and hooks[0][1]["previous"] == "ok"
    assert LogEntry.objects.filter(event=event, text__startswith="Down: Thing 0", important=True).exists()
    assert AuditLog.objects.filter(action="heartbeat.down").count() == 1
    # still down: nothing new
    assert services.evaluate(event, T0 + dt.timedelta(seconds=200)) == []
    fake.set("ok")
    with django_capture_on_commit_callbacks(execute=True):
        services.evaluate(event, T0 + dt.timedelta(seconds=300))
        [back] = services.evaluate(event, T0 + dt.timedelta(seconds=361))
    assert (back.old, back.new) == ("down", "ok")
    up = Notification.objects.filter(user=control).latest("created_at")
    assert up.title == "Back up: Fake: Thing 0" and "about 4 min" in up.body
    assert [k for k, _p in hooks] == ["heartbeat.down", "heartbeat.recovered"]
    assert not HealthState.objects.get(event=event, check_key="fake", item="k0").alerted


def test_warn_changes_at_once_and_quietly(event, fake, control):
    live(event)
    fake.set("ok")
    services.evaluate(event, T0)
    fake.set("warn")
    [c] = services.evaluate(event, T0 + dt.timedelta(seconds=1))
    assert (c.old, c.new) == ("ok", "warn")
    assert not Notification.objects.exists()


def test_no_alert_outside_alert_states_and_new_items(event, fake, control):
    fake.set("down")
    services.evaluate(event, T0)  # first sight: waits for the grace like any change
    assert HealthState.objects.get(check_key="fake").status == "unknown"
    [c] = services.evaluate(event, T0 + dt.timedelta(minutes=2))
    assert c.new == "down" and not Notification.objects.exists()  # draft event: not alerted
    fake.set("ok")
    services.evaluate(event, T0 + dt.timedelta(minutes=3))
    services.evaluate(event, T0 + dt.timedelta(minutes=5))
    assert not Notification.objects.exists()  # no recovery for an outage nobody was told about
    fake.items = []
    services.evaluate(event, T0 + dt.timedelta(minutes=6))
    assert not HealthState.objects.filter(check_key="fake").exists()  # gone items are forgotten


def test_many_changes_are_one_message(event, fake, control, hooks, django_capture_on_commit_callbacks):
    live(event)
    fake.set(*["ok"] * 6)
    services.evaluate(event, T0)
    fake.set(*["down"] * 6)
    with django_capture_on_commit_callbacks(execute=True):
        services.evaluate(event, T0 + dt.timedelta(seconds=1))
        assert len(services.evaluate(event, T0 + dt.timedelta(seconds=70))) == 6
    [note] = Notification.objects.filter(user=control)
    assert note.title == "Down: 6 × Fake" and "Thing 0" in note.body
    assert [k for k, _p in hooks].count("heartbeat.down") == 6


def test_instance_alerts_go_to_admins(db, admin, fake, django_capture_on_commit_callbacks):
    fake.set("down")
    with django_capture_on_commit_callbacks(execute=True):
        services.evaluate(None, T0)
        services.evaluate(None, T0 + dt.timedelta(minutes=2))
    note = Notification.objects.get(user=admin)
    assert note.title == "Down: Fake: Thing 0" and note.url == "/settings/heartbeat/"


def test_beat_task_and_module_off(event, fake, admin):
    live(event)
    fake.set("down")
    tasks.evaluate()
    assert Pulse.objects.filter(key="celery").exists()
    assert HealthState.objects.filter(event=event, check_key="fake").exists()
    assert HealthState.objects.filter(event=None, check_key="celery", status="ok").exists()
    modules.set_event(event, "heartbeat", False)
    HealthState.objects.all().delete()
    tasks.evaluate()
    assert not HealthState.objects.filter(event=event).exists()


# ------------------------------------------------------------------ operator check-in
def checkin_on(event, **kw):
    values = {"checkin_enabled": True, "checkin_interval_minutes": 30, "checkin_grace_minutes": 5,
              "checkin_roles": ["control-room"], "checkin_escalation": ["orga", "admin"], **kw}
    settings_store.save("heartbeat", "event", str(event.pk), values)


def test_checkin_off_by_default_and_live_only(event, control):
    assert not checkin.status(event).enabled
    assert checkin.escalate_due(event, T0) == 0
    checkin_on(event)
    assert checkin.status(event).enabled and not checkin.status(event).active  # draft
    live(event, "setup")
    assert checkin.escalate_due(event, T0) == 0 and not checkin.status(event).active
    checkin_on(event, checkin_live_only=False)
    assert checkin.status(event).active


def test_escalation_order_and_timing(event, admin, control, orga_user, hooks, channel,
                                     django_capture_on_commit_callbacks):
    live(event)
    checkin_on(event, checkin_channels=["fake"])
    with django_capture_on_commit_callbacks(execute=True):
        assert checkin.escalate_due(event, T0) == 0  # armed now
        assert checkin.status(event, T0).due_at == T0 + dt.timedelta(minutes=30)
        assert checkin.escalate_due(event, T0 + dt.timedelta(minutes=29)) == 0
        assert checkin.escalate_due(event, T0 + dt.timedelta(minutes=30)) == 1  # reminder
        assert Notification.objects.filter(user=control, title__startswith="Check-in due").exists()
        assert not Notification.objects.filter(user=orga_user).exists()
        assert not OutboxJob.objects.filter(kind="core.alert").exists()  # reminders stay in the app
        assert checkin.escalate_due(event, T0 + dt.timedelta(minutes=34)) == 0
        assert checkin.escalate_due(event, T0 + dt.timedelta(minutes=35)) == 1  # step 1: orga
        assert Notification.objects.filter(user=orga_user, title__startswith="Missed check-in").exists()
        assert not Notification.objects.filter(user=admin, title__startswith="Missed").exists()
        assert checkin.escalate_due(event, T0 + dt.timedelta(minutes=35)) == 0  # once
        assert checkin.escalate_due(event, T0 + dt.timedelta(minutes=40)) == 1  # step 2: admin
        assert Notification.objects.filter(user=admin, title__startswith="Missed check-in").exists()
        assert checkin.escalate_due(event, T0 + dt.timedelta(hours=2)) == 0  # chain exhausted
    steps = list(CheckInEscalation.objects.filter(event=event).order_by("step").values_list("step", "roles"))
    assert steps == [(0, ["control-room"]), (1, ["orga"]), (2, ["admin"])]
    assert OutboxJob.objects.filter(kind="core.alert").count() == 2
    assert [p["step"] for k, p in hooks if k == "heartbeat.checkin_missed"] == [1, 2]
    assert AuditLog.objects.filter(action="heartbeat.checkin_escalated").count() == 2
    assert AuditLog.objects.filter(action="heartbeat.checkin_reminder").count() == 1
    st = checkin.status(event, T0 + dt.timedelta(minutes=41))
    assert st.overdue and st.steps == 2
    # a check-in ends it and tells the escalated roles
    with django_capture_on_commit_callbacks(execute=True):
        checkin.check_in(event, control, now=T0 + dt.timedelta(minutes=42))
    assert Notification.objects.filter(user=orga_user, title__startswith="Check-in received").exists()
    assert AuditLog.objects.filter(action="heartbeat.checkin", actor_id=control.pk).exists()
    assert [p["late"] for k, p in hooks if k == "heartbeat.checked_in"] == [True]
    st = checkin.status(event, T0 + dt.timedelta(minutes=43))
    assert not st.overdue and st.due_at == T0 + dt.timedelta(minutes=72)
    assert checkin.escalate_due(event, T0 + dt.timedelta(minutes=71)) == 0
    assert checkin.escalate_due(event, T0 + dt.timedelta(minutes=72)) == 1


def test_checkin_permissions_and_disarm(event, member, control, admin, monkeypatch):
    from django.core.exceptions import PermissionDenied, ValidationError

    live(event)
    checkin_on(event)
    assert checkin.may_check_in(control, event) and checkin.may_check_in(admin, event)  # admin: heartbeat.manage
    assert not checkin.may_check_in(member, event)
    with pytest.raises(PermissionDenied):
        checkin.check_in(event, member)
    ci = checkin.check_in(event, control, now=T0, source="staff")
    assert ci.source == "staff" and checkin.status(event, T0).armed_at == T0  # a check-in arms at once
    live(event, "teardown")
    checkin.escalate_due(event, T0 + dt.timedelta(hours=1))
    assert checkin.status(event).armed_at is None
    from apps.nodes import guard

    live(event)
    monkeypatch.setattr(guard, "remote", lambda e: True)
    with pytest.raises(ValidationError):
        checkin.check_in(event, control)
    assert checkin.escalate_due(event, T0 + dt.timedelta(hours=5)) == 0


# ------------------------------------------------------------------ pages, panel, staff card, widget
def test_pages_permissions_and_module_switch(client, event, member, other, admin):
    client.force_login(other)
    assert client.get("/e/demo/heartbeat/").status_code == 404  # not a member
    client.force_login(member)
    r = client.get("/e/demo/heartbeat/")
    assert r.status_code == 200 and b"Background worker" in r.content and b"Operator check-in is off" in r.content
    assert client.get("/settings/heartbeat/").status_code == 403
    assert client.post("/e/demo/heartbeat/check-in/").status_code == 403
    modules.set_event(event, "heartbeat", False)
    assert client.get("/e/demo/heartbeat/").status_code == 404
    login_2fa(client, admin)
    r = client.get("/settings/heartbeat/")
    assert r.status_code == 200 and b"Outbox" in r.content
    modules.set_instance("heartbeat", False)
    assert client.get("/settings/heartbeat/").status_code == 404


def test_checkin_view_panel_and_staff_card(client, event, control, fake):
    live(event)
    checkin_on(event)
    fake.set("down")
    login_2fa(client, control)
    r = client.get("/e/demo/staff/")
    assert b"I&#x27;m here" in r.content or b"I'm here" in r.content
    r = client.get("/e/demo/ops/control/")
    assert r.status_code == 200 and b"Heartbeat" in r.content and b"Thing 0" in r.content
    r = client.get("/e/demo/ops/control/panel/heartbeat.health/", HTTP_HX_CURRENT_URL="http://testserver/e/demo/ops/control/")
    assert r.status_code == 200 and b'value="http://testserver/e/demo/ops/control/"' in r.content
    r = client.post("/e/demo/heartbeat/check-in/", {"source": "dashboard", "next": "/e/demo/ops/control/"})
    assert r.status_code == 302 and r["Location"] == "/e/demo/ops/control/"
    assert CheckIn.objects.get(event=event).source == "dashboard"
    r = client.get("/e/demo/heartbeat/")
    assert b"Recent check-ins" in r.content and b"Control" in r.content


def test_alive_widget_and_data_source(client, event, admin):
    from apps.content import plugin_widgets

    w = plugin_widgets.widgets(event)["heartbeat.alive"]
    assert w["element"] == "evac-heartbeat-alive" and w["script"].endswith("heartbeat/alive.js")
    assert w["sources"] == ["heartbeat.alive"] and w["ttl"] == 10
    data = plugin_widgets.source_payload(event, "heartbeat.alive")
    assert data["timezone"] == "Europe/Berlin" and data["server_time"] and data["ttl"] == 10
    login_2fa(client, admin)
    r = client.get("/e/demo/content/sources/heartbeat.alive/")
    assert r.status_code == 200 and r.json()["data"]["timezone"] == "Europe/Berlin"
    modules.set_event(event, "heartbeat", False)
    assert "heartbeat.alive" not in plugin_widgets.widgets(event)


def test_pages_have_no_a11y_findings(client, event, admin, fake):
    live(event)
    checkin_on(event)
    fake.set("down", "warn", "unknown", "ok")
    login_2fa(client, admin)
    checkin.check_in(event, admin)
    for url in ("/e/demo/heartbeat/", "/settings/heartbeat/", "/e/demo/ops/control/", "/e/demo/staff/",
                "/e/demo/settings/s/heartbeat/"):
        assert audit_url(client, url) == [], url
