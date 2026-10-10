# SPDX-License-Identifier: AGPL-3.0-or-later
"""Incidents, ops log, tasks, escalation, the control room and the staff card (roadmap 6.1/6.2, ADR-0039)."""
import datetime as dt
import json

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken, User
from apps.core import modules, settings_store
from apps.core.a11y import audit_url
from apps.core.models import AuditLog, Notification, OutboxJob
from apps.core.plugins import NotificationChannelSpec
from apps.core.registry import registry
from apps.events import services as ev
from apps.ops import services
from apps.ops.models import Escalation, EscalationRule, Incident, IncidentUpdate, LogEntry, Task
from conftest import login_2fa


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


def report(event, admin, **kw):
    kw.setdefault("title", "Fight at gate C")
    kw.setdefault("category", "Security")
    return services.create_incident(Incident(event=event, **kw), actor=admin)


@pytest.fixture
def control(event, role):
    u = User.objects.create_user(email="control@example.org", password="pw-control-123")
    ev.assign_role(event, u, role("control-room"))
    return u


@pytest.fixture
def channel():
    """A fake alert channel."""
    sent = []
    spec = NotificationChannelSpec(key="fake", name="Fake", alert=lambda e, a: sent.append((e, a)) or
                                   {"recipients": 1, "detail": "ok"})
    reg = registry.ensure_loaded().notification_channels
    reg["fake"] = spec
    yield sent
    del reg["fake"]


# ------------------------------------------------------------------ incidents
def test_numbering_timeline_and_log(event, admin, venue):
    from apps.venues.models import Room

    a = report(event, admin, severity="high", room=Room.objects.get(name="Hall A"), location="Bar")
    b = report(event, admin, title="Lost wallet", category="Lost property", severity="low")
    assert (a.number, b.number) == (1, 2)
    assert a.place == "Hall A" and a.evac_scope_chain()[0] == ("room", str(a.room_id))
    assert a.updates.get().kind == IncidentUpdate.Kind.CREATED
    line = LogEntry.objects.get(incident=a)
    assert line.kind == "system" and line.important and "Incident #1 opened" in line.text
    assert AuditLog.objects.filter(action="ops.incident_created").count() == 2
    with pytest.raises(ValidationError, match="title"):
        report(event, admin, title=" ")


def test_status_transitions(event, admin):
    inc = report(event, admin)
    services.set_status(inc, "acknowledged", actor=admin)
    assert inc.acknowledged_at is not None
    services.set_status(inc, "resolved", actor=admin, note="Separated")
    assert inc.resolved_at and inc.updates.filter(kind="status").count() == 2
    with pytest.raises(ValidationError, match="cannot become"):
        services.set_status(inc, "acknowledged", actor=admin)
    with pytest.raises(ValidationError, match="Unknown"):
        services.set_status(inc, "nope", actor=admin)
    services.set_status(inc, "closed", actor=admin)
    services.set_status(inc, "in_progress", actor=admin)  # reopened
    assert inc.closed_at is None and inc.resolved_at is None
    assert LogEntry.objects.filter(text__contains="closed").exists()


def test_edit_assign_note_link(event, admin, member, venue):
    from apps.venues.models import Zone

    inc = report(event, admin)
    before = {f: getattr(inc, f) for f in services.EDITABLE}
    inc.severity, inc.assignee, inc.zone = "critical", member, Zone.objects.get(name="North")
    services.update_incident(inc, ["severity", "assignee", "zone"], actor=admin, before=before)
    kinds = list(inc.updates.values_list("kind", flat=True))
    assert {"severity", "assigned", "edited"} <= set(kinds)
    assert Notification.objects.filter(user=member, title__contains="assigned to you").exists()
    assert services.update_incident(inc, ["status"], actor=admin) is inc  # not editable: nothing happens
    services.add_note(inc, "Police informed", actor=admin)
    photo = SimpleUploadedFile("scene.jpg", b"\xff\xd8\xff" + b"0" * 100, content_type="image/jpeg")
    u = services.add_note(inc, "", actor=admin, attachment=photo)
    assert u.kind == "attachment" and u.attachment_name == "scene.jpg"
    with pytest.raises(ValidationError, match="Attach"):
        services.add_note(inc, "", actor=admin, attachment=SimpleUploadedFile("x.exe", b"MZ"))
    with pytest.raises(ValidationError, match="10 MB"):
        big = SimpleUploadedFile("big.pdf", b"x")
        big.size = 11 * 1024 * 1024
        services.add_note(inc, "", actor=admin, attachment=big)
    with pytest.raises(ValidationError, match="note"):
        services.add_note(inc, " ", actor=admin)
    services.link(inc, kind="announcement", ident="a1", label="Gate C closed", url="/x/")
    services.link(inc, kind="announcement", ident="a1", label="Gate C closed")
    assert len(inc.links) == 1


def test_wrong_venue_rejected(event, admin):
    from apps.venues.models import Venue, Zone

    other = Venue.objects.create(slug="else", name="Elsewhere")
    with pytest.raises(ValidationError, match="another venue"):
        report(event, admin, zone=Zone.objects.create(venue=other, name="Z"))


# ------------------------------------------------------------------ ops log
def test_log_entries_idempotent_and_backdated(event, admin):
    e = services.add_entry(event, "Gate C clear", actor=admin, sender="Security 2", recipient="Control",
                           client_id="abc")
    again = services.add_entry(event, "Gate C clear", actor=admin, client_id="abc")
    assert e.pk == again.pk and LogEntry.objects.count() == 1
    old = timezone.now() - dt.timedelta(minutes=20)
    assert services.add_entry(event, "written offline", actor=admin, at=old).at == old
    future = services.add_entry(event, "clock wrong", actor=admin, at=timezone.now() + dt.timedelta(hours=1))
    assert future.at <= timezone.now()
    with pytest.raises(ValidationError, match="empty"):
        services.add_entry(event, "  ", actor=admin)


@pytest.mark.parametrize("kind,payload,text,important", [
    ("evacuation.state_changed", {"state": "evacuate", "zone_name": "North", "drill": True}, "North: evacuate (drill)",
     True),
    ("evacuation.staff_ack", {"kind": "zone_clear", "user": "Sam", "note": "all out"}, "zone_clear by Sam (all out)",
     False),
    ("evacuation.routes_changed", {}, "Routes changed", False),
    ("screen.offline", {"name": "Foyer"}, "Screen offline: Foyer", False),
    ("screen.online", {"name": "Foyer"}, "Screen back online: Foyer", False),
    ("dial.dect_alert", {"message": "RFP 3 down", "severity": "error"}, "DECT: RFP 3 down", True),
    ("announcement.published", {"title": "Doors open"}, "Announcement sent: Doors open", False),
    ("announcement.cancelled", {"title": "Doors open"}, "Announcement cancelled", False),
    ("override.started", {"title": "Rain"}, "Screen override started: Rain", False),
    ("override.cancelled", {"name": "Rain"}, "Screen override ended: Rain", False),
    ("occupancy.state_changed", {"name": "Hall A", "state": "full", "value": 10, "capacity": 10},
     "Occupancy Hall A: full (10 / 10)", True),
    ("program.session_changed", {"title": "Talk", "status": "cancelled"}, "Program: Talk cancelled", False),
    ("program.session_changed", {"title": "Talk", "moved": True, "stage": "B"}, "moved to B", False),
])
def test_sink_writes_system_lines(event, kind, payload, text, important):
    services.sink(kind, payload, event)
    e = LogEntry.objects.get()
    assert text in e.text and e.important == important and e.source == kind


def test_sink_quiet_cases(event):
    services.sink("program.session_changed", {"title": "Talk", "status": "scheduled"}, event)
    services.sink("member.added", {}, event)
    services.sink("screen.offline", {"name": "x"}, None)
    settings_store.save("ops", "event", str(event.pk), {"log_system_events": False}, event=event)
    services.sink("screen.offline", {"name": "x"}, event)
    modules.set_event(event, "ops", False)
    assert services.system_log(event, "x", source="t") is None
    assert not LogEntry.objects.exists()


# ------------------------------------------------------------------ tasks
def test_tasks(event, admin, member):
    inc = report(event, admin)
    t = services.save_task(Task(event=event, title="Close gate C", assignee=member, incident=inc), actor=admin)
    assert Notification.objects.filter(user=member, title__contains="Task for you").exists()
    services.set_task_done(t, True, actor=member)
    assert t.status == "done" and t.done_by == member
    services.set_task_done(t, False, actor=member)
    assert t.done_at is None and inc.updates.filter(text__contains="Task reopened").exists()
    with pytest.raises(ValidationError):
        services.save_task(Task(event=event, title=""), actor=admin)


# ------------------------------------------------------------------ escalation
def test_escalation_now_and_later(event, admin, control, role, channel, django_capture_on_commit_callbacks):
    now_rule = EscalationRule(event=event, name="High: control", min_severity="high", channels=["fake", "gone"])
    services.save_rule(now_rule, actor=admin, roles=[role("control-room")])
    late = EscalationRule(event=event, name="Medical after 5", min_severity="medium", after_minutes=5,
                          categories=["Medical"])
    services.save_rule(late, actor=admin, roles=[role("control-room")])
    with django_capture_on_commit_callbacks(execute=True):
        low = report(event, admin, severity="low")
        high = report(event, admin, severity="high")
        med = report(event, admin, severity="medium", category="Medical")
    assert not low.escalations.exists()
    esc = high.escalations.get()
    assert esc.recipients == 1 and esc.channels == ["fake"]
    assert Notification.objects.filter(user=control, title__contains="Incident #2 (High)").exists()
    job = OutboxJob.objects.get(kind="core.alert")
    from apps.core import outbox

    with django_capture_on_commit_callbacks(execute=True):
        assert outbox.deliver(job)
    assert channel[0][1].title.startswith("Incident #2") and channel[0][1].key == f"incident:{high.pk}:{now_rule.pk}"
    assert not med.escalations.exists()
    later = timezone.now() + dt.timedelta(minutes=6)
    assert services.escalate_due(later) == 1
    assert med.escalations.get().rule_name == "Medical after 5"
    assert services.escalate_due(later) == 0  # once
    services.set_status(low, "acknowledged", actor=admin)
    low.severity = "critical"
    services.update_incident(low, ["severity"], actor=admin, before={"severity": "low"})
    assert services.escalate(low.pk) == 0  # acknowledged already: "unacknowledged" rules stay quiet
    assert LogEntry.objects.filter(text__contains="escalated").count() == 2
    services.delete_rule(late, actor=admin)
    assert Escalation.objects.filter(rule__isnull=True).count() == 1


def test_rule_matching(event, admin):
    inc = report(event, admin, severity="high", category="Fire")
    r = EscalationRule(event=event, name="r", min_severity="high", categories=["Medical"])
    assert not services.rule_matches(r, inc)
    r.categories = []
    assert services.rule_matches(r, inc)
    r.until = "unresolved"
    services.set_status(inc, "in_progress", actor=admin)
    assert services.rule_matches(r, inc)
    r.enabled = False
    assert not services.rule_matches(r, inc)
    with pytest.raises(ValidationError):
        services.save_rule(EscalationRule(event=event, name=""), actor=admin)


# ------------------------------------------------------------------ pages
@pytest.fixture
def staff(client, admin):
    return login_2fa(client, admin)


def test_pages(staff, event, admin, venue):
    inc = report(event, admin, severity="high")
    base = f"/e/{event.slug}/ops/"
    r = staff.post(f"{base}new/", {"title": "Smoke in foyer", "category": "Fire", "severity": "critical",
                                   "note": "Cloakroom"})
    new = Incident.objects.get(title="Smoke in foyer")
    assert r.status_code == 302 and new.updates.get().text == "Cloakroom"
    assert staff.get(f"{base}?show=all&severity=high&category=Security&q=gate").status_code == 200
    assert staff.get(f"{base}?show=resolved").status_code == 200
    page = staff.get(f"{base}{inc.pk}/")
    assert b"Fight at gate C" in page.content and b"Acknowledged" in page.content
    staff.post(f"{base}{inc.pk}/status/", {"status": "acknowledged"})
    staff.post(f"{base}{inc.pk}/status/", {"status": "new"})  # refused, message
    inc.refresh_from_db()
    assert inc.status == "acknowledged"
    staff.post(f"{base}{inc.pk}/edit/", {"title": "Fight at gate C", "category": "Security", "severity": "medium",
                                         "team": "Security"})
    inc.refresh_from_db()
    assert inc.severity == "medium" and inc.team == "Security"
    photo = SimpleUploadedFile("p.png", b"\x89PNG\r\n" + b"0" * 50, content_type="image/png")
    staff.post(f"{base}{inc.pk}/note/", {"text": "photo", "attachment": photo})
    u = inc.updates.get(kind="attachment")
    resp = staff.get(f"{base}files/{u.pk}/")
    assert resp.status_code == 200 and resp["X-Content-Type-Options"] == "nosniff"
    assert staff.post(f"{base}{inc.pk}/note/", {"text": ""}).status_code == 302
    staff.post(f"{base}log/", {"text": "Gate C clear", "sender": "Sec 2", "recipient": "Control",
                               "client_id": "c1", "written_at": ""})
    staff.post(f"{base}log/", {"text": "Gate C clear", "client_id": "c1"})
    assert LogEntry.objects.filter(kind="message").count() == 1
    assert staff.get(f"{base}log/?only=important&q=gate").status_code == 200
    staff.post(f"{base}tasks/", {"title": "Check barrier", "incident": str(inc.pk), "next": f"{base}{inc.pk}/"})
    t = Task.objects.get(title="Check barrier")
    staff.post(f"{base}tasks/{t.pk}/done/", {"done": "1"})
    t.refresh_from_db()
    assert t.status == "done"
    assert staff.get(f"{base}tasks/?show=mine").status_code == 200
    staff.post(f"{base}escalation/", {"name": "All high", "enabled": "on", "min_severity": "high",
                                      "after_minutes": "0", "until": "unacknowledged"})
    rule = EscalationRule.objects.get(name="All high")
    assert staff.get(f"{base}escalation/{rule.pk}/").status_code == 200
    staff.post(f"{base}escalation/{rule.pk}/delete/")
    assert not EscalationRule.objects.exists()


def test_report_export(staff, event, admin):
    report(event, admin, title="=HYPERLINK(evil)")
    csv = staff.get(f"/e/{event.slug}/ops/report/").content.decode()
    assert "'=HYPERLINK" in csv and csv.startswith("number,")
    data = json.loads(staff.get(f"/e/{event.slug}/ops/report/?format=json").content)
    assert data["incidents"][0]["number"] == 1 and data["ops_log"]
    assert AuditLog.objects.filter(action="ops.report_exported").count() == 2


def test_permissions_and_module_switch(client, event, member, admin, role):
    inc = report(event, admin)
    login_2fa(client, member)  # viewer: sees, cannot report or change
    base = f"/e/{event.slug}/ops/"
    assert client.get(base).status_code == 200
    assert client.get(f"{base}new/").status_code == 403
    assert client.post(f"{base}{inc.pk}/status/", {"status": "acknowledged"}).status_code == 403
    assert client.get(f"{base}escalation/").status_code == 403
    assert client.get(f"{base}report/").status_code == 403
    assert client.post(f"{base}log/", {"text": "x"}).status_code == 403
    modules.set_event(event, "ops", False)
    assert client.get(base).status_code == 404


def test_staff_card_offline_forms(client, event, role, admin):
    sec = User.objects.create_user(email="sec@example.org", password="pw-sec-123456")
    ev.assign_role(event, sec, role("security"))
    login_2fa(client, sec)
    staff_page = client.get(f"/e/{event.slug}/staff/")
    assert b"Report an incident" in staff_page.content and b"data-client-id" in staff_page.content
    form = {"title": "Smoke", "severity": "high", "category": "Fire", "location": "Foyer", "client_id": "q1",
            "next": f"/e/{event.slug}/staff/"}
    client.post(f"/e/{event.slug}/ops/staff/report/", form)
    client.post(f"/e/{event.slug}/ops/staff/report/", form, HTTP_X_EVAC_QUEUED="1")  # replay
    inc = Incident.objects.get()
    assert inc.source == "staff" and inc.reported_by
    client.post(f"/e/{event.slug}/ops/staff/report/", {"title": "", "severity": "high"})
    assert Incident.objects.count() == 1
    client.post(f"/e/{event.slug}/ops/staff/log/", {"text": "On my way", "client_id": "l1",
                                                     "written_at": "2026-01-01T00:00:00+00:00"})
    assert LogEntry.objects.get(kind="message").sender == str(sec)
    client.post(f"/e/{event.slug}/ops/staff/{inc.pk}/ack/")
    inc.refresh_from_db()
    assert inc.status == "acknowledged" and inc.assignee == sec
    client.post(f"/e/{event.slug}/ops/staff/{inc.pk}/ack/")  # replay: nothing changes
    assert client.post(f"/e/{event.slug}/ops/staff/00000000-0000-0000-0000-000000000000/ack/").status_code == 302


# ------------------------------------------------------------------ control room
def test_control_room(staff, event, admin, venue):
    from apps.venues.models import Floor, Zone

    floor = Floor.objects.get(name="Ground")
    z = Zone.objects.get(name="North")
    z.areas = [{"floor": str(floor.pk), "points": [[0, 0], [10, 0], [10, 10], [0, 10]]}]
    z.save()
    report(event, admin, severity="critical", zone=z)
    page = staff.get(f"/e/{event.slug}/ops/control/")
    assert b"Open incidents" in page.content and b"<polygon" in page.content and b"zone-crit" in page.content
    assert b'hx-trigger="every 5s"' in page.content
    assert staff.get(f"/e/{event.slug}/ops/control/panel/ops.map/").status_code == 200
    assert staff.get(f"/e/{event.slug}/ops/control/panel/nope/").status_code == 404
    modules.set_event(event, "crowd", False)
    assert staff.get(f"/e/{event.slug}/ops/control/panel/crowd.occupancy/").status_code == 404
    assert b"Occupancy" not in staff.get(f"/e/{event.slug}/ops/control/").content


def test_pages_are_accessible(staff, event, admin):
    inc = report(event, admin)
    for url in ("", "control/", "new/", f"{inc.pk}/", "log/", "tasks/", "escalation/"):
        assert audit_url(staff, f"/e/{event.slug}/ops/{url}") == [], url


# ------------------------------------------------------------------ API
@pytest.fixture
def api(event, admin):
    _tok, raw = ServiceToken.issue(name="radio", owner=admin, scopes=["ops:read", "ops:write"], event=event)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    return c


def test_api(api, event, admin):
    base = f"/api/v1/events/{event.slug}/incidents/"
    r = api.post(base, {"title": "Sensor: smoke", "category": "Fire", "severity": "high"}, format="json")
    assert r.status_code == 201 and r.json()["number"] == 1
    pk = r.json()["id"]
    assert api.post(base, {"title": "x", "category": "Nope"}, format="json").status_code == 400
    assert api.patch(f"{base}{pk}/", {"severity": "critical"}, format="json").json()["severity"] == "critical"
    assert api.post(f"{base}{pk}/status/", {"status": "resolved"}, format="json").json()["status"] == "resolved"
    assert api.post(f"{base}{pk}/status/", {"status": "new"}, format="json").status_code == 400
    assert api.post(f"{base}{pk}/note/", {"text": "Alarm reset"}, format="json").status_code == 200
    rows = api.get(base, {"status": "open"}).json()
    assert (rows.get("results", rows) if isinstance(rows, dict) else rows) == []
    log = f"/api/v1/events/{event.slug}/ops-log/"
    for _ in range(2):
        assert api.post(log, {"text": "Gate C clear", "sender": "Sec 2", "client_id": "r1"},
                        format="json").status_code == 201
    assert LogEntry.objects.filter(kind="message").count() == 1
    rows = api.get(log).json()
    assert len(rows.get("results", rows) if isinstance(rows, dict) else rows) >= 2
    modules.set_event(event, "ops", False)
    assert api.get(base).status_code == 404


def test_api_permissions(event, member):
    _tok, raw = ServiceToken.issue(name="v", owner=member, scopes=["ops:read", "ops:write"], event=event)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert c.get(f"/api/v1/events/{event.slug}/incidents/").status_code == 200
    assert c.post(f"/api/v1/events/{event.slug}/incidents/", {"title": "x", "category": "Other"},
                  format="json").status_code == 403


def test_demo_seed(event, admin, venue):
    from apps.ops import demo

    assert demo.seed(event, admin) == 4
    assert demo.seed(event, admin) == 0
    assert Incident.objects.filter(status="resolved").count() == 1 and Task.objects.count() == 2


def test_sync_spec_lists_attachments(event, admin):
    from apps.ops import sync

    inc = report(event, admin)
    u = services.add_note(inc, "", actor=admin, attachment=SimpleUploadedFile("a.pdf", b"%PDF"))
    spec = {m.label: m for m in sync.spec().models}
    assert spec["ops.IncidentUpdate"].files(u)[0][0] == u.attachment.name
    assert spec["ops.Incident"].live


