# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trigger sources, armed requests, the two-person rule, scheduled drills, panic page and API (ADR-0031)."""
from datetime import timedelta
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.accounts.models import ServiceToken, User
from apps.core import settings_store
from apps.core.a11y import check_html
from apps.core.models import AuditLog, Notification
from apps.evacuation import services, tasks, triggers
from apps.evacuation.machine import Refused, State
from apps.evacuation.models import EvacRequest, ScheduledDrill
from apps.events import services as event_services
from conftest import login_2fa

from .conftest import tf

URL = "/e/demo/evacuation/"


def later(seconds):
    return mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(seconds=seconds))


def shown(event):
    return services.effective_for(event, []).state


@pytest.fixture
def second(event, role):
    u = User.objects.create_user(email="second@example.org", password="pw-12345678x")
    event_services.assign_role(event, u, role("control-room"))
    return u


def two_person(event, states=("evacuate",), seconds=60):
    settings_store.save("evacuation", "event", str(event.pk), {"model": "zones", "two_person_states": list(states),
                                                               "two_person_seconds": seconds}, event=event)


def test_web_executes_and_api_arms(event, admin, second):
    out = triggers.trigger(event, "attention", source="web", actor=admin, request=tf(admin))
    assert out.result == "executed" and shown(event) is State.ATTENTION and out.request is None
    out = triggers.trigger(event, "evacuate", source="api", actor=admin, request=tf(admin), reason="BMA zone 3")
    assert out.result == "armed" and shown(event) is State.ATTENTION
    req = out.request
    assert req.deadline - req.created_at == timedelta(seconds=120) and req.status == "pending"
    # the control room (with the trigger permission) is alerted
    assert Notification.objects.filter(user=second, title__startswith="Alarm to confirm").exists()
    triggers.confirm(req, actor=second, request=tf(second))
    req.refresh_from_db()
    assert req.status == "confirmed" and req.decided_by == second and shown(event) is State.EVACUATE
    assert AuditLog.objects.filter(action="evacuation.armed").exists()
    assert AuditLog.objects.filter(action="evacuation.request_confirmed").exists()
    with pytest.raises(Refused):
        triggers.confirm(req, actor=second, request=tf(second))


def test_armed_alarm_escalates_when_nobody_answers(event, admin):
    out = triggers.trigger(event, "evacuate", source="bridge", actor=None, check_perms=False)
    assert out.result == "armed"
    with later(60):
        assert triggers.process_due() == 0
    with later(121):
        assert tasks.process_due.run() == 1
    out.request.refresh_from_db()
    assert out.request.status == "escalated" and shown(event) is State.EVACUATE
    assert AuditLog.objects.filter(action="evacuation.request_escalated").exists()


def test_reject_and_superseded(event, admin, second):
    a = triggers.trigger(event, "attention", source="api", actor=admin, request=tf(admin)).request
    triggers.reject(a, actor=second, request=tf(second))
    a.refresh_from_db()
    assert a.status == "rejected" and shown(event) is State.NORMAL
    with pytest.raises(Refused):
        triggers.reject(a, actor=second, request=tf(second))
    b = triggers.trigger(event, "attention", source="api", actor=admin, request=tf(admin)).request
    triggers.trigger(event, "attention", source="web", actor=admin, request=tf(admin))  # set meanwhile
    triggers.confirm(b, actor=second, request=tf(second))
    b.refresh_from_db()
    assert b.status == "superseded"
    # nobody without the permission decides
    c = triggers.trigger(event, "evacuate", source="api", actor=admin, request=tf(admin)).request
    viewer = User.objects.create_user(email="v@example.org", password="pw-12345678x")
    for fn in (triggers.confirm, triggers.reject):
        with pytest.raises(PermissionDenied):
            fn(c, actor=viewer, request=tf(viewer))


def test_policy_rules(event, admin, zones):
    north = zones["North"]
    triggers.save_policy(event, source="api", state="", zone=None, action="notify", escalate_seconds=99,
                         actor=admin)
    out = triggers.trigger(event, "evacuate", source="api", actor=admin, request=tf(admin))
    assert out.result == "notified" and out.request.status == "notified" and shown(event) is State.NORMAL
    triggers.save_policy(event, source="api", state="evacuate", zone=north, action="execute",
                         escalate_seconds=99, actor=admin)
    out = triggers.trigger(event, "evacuate", source="api", zone=north, actor=admin, request=tf(admin))
    assert out.result == "executed"
    p = triggers.save_policy(event, source="web", state="", zone=None, action="arm", escalate_seconds=None,
                             actor=admin)
    out = triggers.trigger(event, "attention", source="web", actor=admin, request=tf(admin))
    assert out.result == "armed" and out.request.deadline is None
    with later(10 ** 6):
        triggers.process_due()
    out.request.refresh_from_db()
    assert out.request.status == "pending"  # waits for a person
    triggers.delete_policy(event, str(p.pk), actor=admin)
    triggers.delete_policy(event, str(p.pk), actor=admin)
    assert "web/*/*: arm" in str(p)
    assert AuditLog.objects.filter(action="evacuation.policy_deleted").count() == 1


def test_two_person_rule(event, admin, second):
    two_person(event)
    out = triggers.trigger(event, "evacuate", source="web", actor=admin, request=tf(admin))
    assert out.result == "waiting" and shown(event) is State.NORMAL
    with pytest.raises(Refused) as err:
        triggers.confirm(out.request, actor=admin, request=tf(admin))
    assert err.value.code == "same_person"
    triggers.confirm(out.request, actor=second, request=tf(second))
    assert shown(event) is State.EVACUATE
    # other stages do not need a second person
    assert triggers.trigger(event, "attention", source="web", actor=admin, request=tf(admin)).result == "executed"
    # the requester may withdraw their own request
    mine = triggers.trigger(event, "evacuate", source="panic", actor=admin, request=tf(admin)).request
    triggers.reject(mine, actor=admin, request=tf(admin))


def test_two_person_request_expires_and_alerts(event, admin, second):
    two_person(event, seconds=30)
    out = triggers.trigger(event, "evacuate", source="panic", actor=admin, request=tf(admin))
    with later(31):
        assert triggers.process_due(event) == 1
    out.request.refresh_from_db()
    assert out.request.status == "expired" and shown(event) is State.NORMAL
    assert Notification.objects.filter(user=second, title__startswith="Not executed").exists()
    # an API trigger is not a person: no two-person rule, its policy applies
    assert triggers.trigger(event, "evacuate", source="api", actor=admin, request=tf(admin)).result == "armed"


def test_two_person_all_clear(event, admin, second):
    two_person(event, states=("all_clear",))
    triggers.trigger(event, "evacuate", source="web", actor=admin, request=tf(admin))
    out = triggers.trigger(event, "all_clear", source="web", actor=admin, request=tf(admin))
    assert out.result == "waiting"
    triggers.confirm(out.request, actor=second, request=tf(second))
    assert shown(event) is State.ALL_CLEAR


def test_only_people_end_alarms(event, admin):
    triggers.trigger(event, "evacuate", source="web", actor=admin, request=tf(admin))
    for src in ("api", "bridge", "schedule"):
        with pytest.raises(Refused) as err:
            triggers.trigger(event, "all_clear", source=src, actor=admin, request=tf(admin))
        assert err.value.code == "person_only"


def test_refusals_apply_to_every_source(event, admin, member):
    with pytest.raises(Refused):
        triggers.trigger(event, "all_clear", source="web", actor=admin, request=tf(admin))
    with pytest.raises(PermissionDenied):
        triggers.trigger(event, "evacuate", source="api", actor=member, request=tf(member))
    triggers.trigger(event, "evacuate", source="web", actor=admin, request=tf(admin))
    with pytest.raises(Refused):  # already active: not even armed
        triggers.trigger(event, "evacuate", source="api", actor=admin, request=tf(admin))
    assert not EvacRequest.objects.exists()


def test_idempotency_key(event, admin):
    a = triggers.trigger(event, "attention", source="api", actor=admin, request=tf(admin), key="bma-42")
    b = triggers.trigger(event, "attention", source="api", actor=admin, request=tf(admin), key="bma-42")
    assert b.result == "duplicate" and b.request.pk == a.request.pk and EvacRequest.objects.count() == 1
    triggers.save_policy(event, source="api", state="", zone=None, action="execute", escalate_seconds=None)
    c = triggers.trigger(event, "evacuate", source="api", actor=admin, request=tf(admin), key="bma-43")
    assert c.result == "executed" and c.request.status == "executed"
    assert triggers.trigger(event, "evacuate", source="api", actor=admin, key="bma-43").result == "duplicate"


def test_scheduled_drills(event, admin, zones):
    now = timezone.now()
    d1 = triggers.schedule_drill(event, at=now - timedelta(minutes=1), state="evacuate", zone=None, note="Q3",
                                 actor=admin)
    d2 = triggers.schedule_drill(event, at=now - timedelta(hours=2), state="attention", zone=None, actor=admin)
    d3 = triggers.schedule_drill(event, at=now + timedelta(hours=1), state="attention", zone=None, actor=admin)
    assert triggers.process_due() == 1
    d1.refresh_from_db(), d2.refresh_from_db(), d3.refresh_from_db()
    assert d1.outcome == "executed" and "missed" in d2.outcome and d3.started_at is None
    status = services.effective_for(event, [])
    assert status.state is State.EVACUATE and status.drill
    # a drill never starts during a real alarm
    triggers.trigger(event, "attention", source="web", actor=admin, request=tf(admin))
    d4 = triggers.schedule_drill(event, at=now, state="evacuate", zone=None, actor=admin)
    triggers.start_due_drills(event)
    d4.refresh_from_db()
    assert d4.outcome.startswith("not started")
    triggers.delete_drill(event, str(d3.pk), actor=admin)
    triggers.delete_drill(event, str(d1.pk), actor=admin)  # started: kept
    assert set(ScheduledDrill.objects.values_list("pk", flat=True)) == {d1.pk, d2.pk, d4.pk}
    assert "Drill evacuate" in str(d1)


def test_sources_include_extensions(event):
    keys = [k for k, _n in triggers.sources()]
    assert keys[:5] == ["web", "panic", "api", "bridge", "schedule"] and len(keys) == len(set(keys))


# ------------------------------------------------------------------------------------------- pages
def test_control_page_pending_and_decide(admin_client, event, admin, second):
    req = triggers.trigger(event, "evacuate", source="api", actor=admin, request=tf(admin)).request
    html = admin_client.get(URL).content.decode()
    assert check_html(html) == [] and "Waiting for a decision" in html and "Executes by itself" in html
    r = admin_client.post(f"{URL}requests/{req.pk}/confirm/", follow=True)
    assert "Confirmed" in r.content.decode() and shown(event) is State.EVACUATE
    r = admin_client.post(f"{URL}requests/{req.pk}/reject/", follow=True)
    assert "already decided" in r.content.decode()
    r = admin_client.post(f"{URL}requests/00000000-0000-0000-0000-000000000000/confirm/", follow=True)
    assert "Unknown request" in r.content.decode()
    other = triggers.trigger(event, "shelter_in_place", source="api", actor=admin, request=tf(admin)).request
    r = admin_client.post(f"{URL}requests/{other.pk}/reject/", {"next": "panic"})
    assert r.status_code == 302 and r["Location"].endswith("/evacuation/panic/")


def test_decide_without_permission(client, event, admin, member):
    req = triggers.trigger(event, "evacuate", source="api", actor=admin, request=tf(admin)).request
    login_2fa(client, member)
    r = client.post(f"{URL}requests/{req.pk}/confirm/", follow=True)
    assert "may not decide" in r.content.decode()


def test_control_page_two_person_message(admin_client, event):
    two_person(event)
    r = admin_client.post(f"{URL}change/", {"scope": "event", "state": "evacuate"}, follow=True)
    assert "Waiting for a second person" in r.content.decode() and shown(event) is State.NORMAL
    settings_store.save("evacuation", "event", str(event.pk), {"model": "zones"}, event=event)
    triggers.save_policy(event, source="web", state="", zone=None, action="arm", escalate_seconds=None)
    r = admin_client.post(f"{URL}change/", {"scope": "event", "state": "attention"}, follow=True)
    assert "Armed" in r.content.decode()
    triggers.save_policy(event, source="web", state="", zone=None, action="notify", escalate_seconds=None)
    r = admin_client.post(f"{URL}change/", {"scope": "event", "state": "staff_alert"}, follow=True)
    assert "control room was notified" in r.content.decode()


def test_panic_page(admin_client, event, zones):
    html = admin_client.get(f"{URL}panic/").content.decode()
    assert check_html(html) == [] and "Raise an alarm" in html and 'value="evacuate"' in html
    north = zones["North"]
    r = admin_client.post(f"{URL}panic/", {"state": "evacuate", "zone": str(north.pk), "reason": "fire"},
                          follow=True)
    assert services.effective_for(event, [str(north.pk)]).state is State.EVACUATE and r.status_code == 200
    r = admin_client.post(f"{URL}panic/", {"state": "evacuate", "zone": str(north.pk)}, follow=True)
    assert "already active" in r.content.decode()
    r = admin_client.post(f"{URL}panic/", {"state": "bogus"}, follow=True)
    assert "Unknown state" in r.content.decode()


def test_panic_page_permissions(client, event, member, role):
    login_2fa(client, member)
    html = client.get(f"{URL}panic/").content.decode()
    assert "may not raise alarms" in html
    assert client.post(f"{URL}panic/", {"state": "evacuate"}).status_code == 403
    crew = User.objects.create_user(email="crew@example.org", password="pw-12345678x")
    event_services.assign_role(event, crew, role("security"))
    client.logout()
    login_2fa(client, crew)
    with mock.patch("apps.evacuation.triggers.trigger", side_effect=PermissionDenied):
        r = client.post(f"{URL}panic/", {"state": "evacuate"}, follow=True)
    assert "may not raise this alarm" in r.content.decode()


def test_staff_card(admin_client, event, admin, member, client):
    triggers.trigger(event, "evacuate", source="api", actor=admin, request=tf(admin))
    html = admin_client.get("/e/demo/staff/").content.decode()
    assert "Raise an alarm" in html and "waits for a decision" in html
    from apps.evacuation import staff

    req = tf(member)
    assert staff.card(req, event)["can_raise"] is False
    outsider = User.objects.create_user(email="out@example.org", password="pw-12345678x")
    assert staff.card(tf(outsider), event) is None


def test_policies_page(admin_client, event, zones):
    html = admin_client.get(f"{URL}policies/").content.decode()
    assert check_html(html) == [] and "Built-in defaults" in html and "Hardware bridge" in html
    r = admin_client.post(f"{URL}policies/", {"what": "policy", "policy-source": "api", "policy-state": "evacuate",
                                               "policy-zone": str(zones["North"].pk), "policy-action": "arm",
                                               "policy-escalate_seconds": "30"}, follow=True)
    assert "Policy saved" in r.content.decode() and "30 s" in r.content.decode()
    r = admin_client.post(f"{URL}policies/", {"what": "policy", "policy-source": "nope", "policy-action": "arm"})
    assert r.status_code == 400
    at = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    r = admin_client.post(f"{URL}policies/", {"what": "drill", "drill-at": at, "drill-state": "evacuate",
                                               "drill-note": "Q4"}, follow=True)
    assert "Drill scheduled" in r.content.decode() and "planned" in r.content.decode()
    r = admin_client.post(f"{URL}policies/", {"what": "drill", "drill-at": "", "drill-state": "evacuate"})
    assert r.status_code == 400
    from apps.evacuation.models import EvacPolicy

    pol, drill = EvacPolicy.objects.get(), ScheduledDrill.objects.get()
    admin_client.post(f"{URL}policies/", {"what": "delete_policy", "pk": str(pol.pk)})
    admin_client.post(f"{URL}policies/", {"what": "delete_drill", "pk": str(drill.pk)})
    admin_client.post(f"{URL}policies/", {"what": "delete_drill", "pk": "nope"})
    assert not EvacPolicy.objects.exists() and not ScheduledDrill.objects.exists()
    settings_store.save("evacuation", "event", str(event.pk), {"model": "zones", "two_person_states": ["evacuate"]},
                        event=event)
    assert "Two-person rule: Evacuate" in admin_client.get(f"{URL}policies/").content.decode()


def test_policies_page_needs_manage(client, event, member):
    login_2fa(client, member)
    assert client.get(f"{URL}policies/").status_code == 403


# ------------------------------------------------------------------------------------------- API
def api(client, token, method, path, data=None):
    fn = getattr(client, method)
    return fn(f"/api/v1/events/demo/evacuation/{path}", data=data, content_type="application/json",
              HTTP_AUTHORIZATION=f"Bearer {token}")


@pytest.fixture
def token(event, admin):
    _tok, raw = ServiceToken.issue(name="BMA gateway", owner=admin, event=event, scopes=["evacuation:write"],
                                   created_with_2fa=True)
    return raw


def test_api(client, event, admin, token, zones):
    r = api(client, token, "get", "")
    assert r.status_code == 200 and r.json()["event"]["state"] == "normal" and r.json()["model"] == "zones"
    r = api(client, token, "post", "trigger/", {"state": "evacuate", "zone": str(zones["North"].pk),
                                                 "key": "k1", "reason": "BMA"})
    assert r.status_code == 201 and r.json()["result"] == "armed" and r.json()["status"] == "pending"
    r = api(client, token, "post", "trigger/", {"state": "evacuate", "zone": str(zones["North"].pk), "key": "k1"})
    assert r.status_code == 200 and r.json()["result"] == "duplicate"
    body = api(client, token, "get", "").json()
    assert body["pending"][0]["state"] == "evacuate" and body["blocked"] == []
    assert api(client, token, "post", "trigger/", {"state": "all_clear"}).status_code == 400
    assert api(client, token, "post", "trigger/", {"state": "evacuate", "source": "web"}).status_code == 400
    r = api(client, token, "post", "trigger/", {"state": "evacuate", "zone": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 400
    r = api(client, token, "post", "trigger/", {"state": "attention", "source": "bridge"})
    assert r.status_code == 201
    triggers.trigger(event, "evacuate", source="web", actor=admin, request=tf(admin))
    r = api(client, token, "post", "trigger/", {"state": "evacuate"})
    assert r.status_code == 400 and r.json()["code"] == "unchanged"
    assert api(client, token, "get", "").json()["event"]["state"] == "evacuate"


def test_api_permissions(client, event, admin, member, zones):
    _t, no2fa = ServiceToken.issue(name="x", owner=admin, event=event, scopes=["evacuation:write"])
    r = api(client, no2fa, "post", "trigger/", {"state": "evacuate"})
    assert r.status_code == 403  # sensitive permission: the token must be created in a two-factor session
    _t, read = ServiceToken.issue(name="r", owner=admin, event=event, scopes=["evacuation:read"],
                                  created_with_2fa=True)
    assert api(client, read, "get", "").status_code == 200
    assert api(client, read, "post", "trigger/", {"state": "evacuate"}).status_code == 403
    from apps.core import modules

    modules.set_event(event, "evacuation", False)
    assert api(client, read, "get", "").status_code == 404
