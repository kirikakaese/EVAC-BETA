# SPDX-License-Identifier: AGPL-3.0-or-later
"""The safety statement is accepted once per event before the evacuation module works there (roadmap 3.11)."""
import json

import pytest
from django.test import Client

from apps.accounts.models import ServiceToken
from apps.core import modules
from apps.core.a11y import check_html
from apps.core.models import AuditLog, ModuleAcknowledgement
from apps.evacuation import bridges
from conftest import login_2fa

pytestmark = pytest.mark.unacknowledged
URL = "/e/demo/evacuation/"


def test_pages_show_the_statement_until_accepted(admin_client, event, admin):
    assert modules.acknowledgement_needed("evacuation", event)
    for path in ("", "panic/", "readiness/", "history/"):
        html = admin_client.get(URL + path).content.decode()
        assert "not a certified fire alarm system" in html and "DIN 14675" in html and check_html(html) == []
    assert admin_client.post(f"{URL}change/", {"scope": "event", "state": "evacuate"}).status_code == 403
    ack = "/e/demo/settings/modules/evacuation/acknowledge/"
    r = admin_client.post(ack, {"next": URL}, follow=True)
    assert "Tick the box" in r.content.decode() and modules.acknowledgement_needed("evacuation", event)
    r = admin_client.post(ack, {"accept": "on", "next": "https://evil.example/"})
    assert r["Location"] == "/e/demo/settings/modules/"
    row = ModuleAcknowledgement.objects.get(event=event, key="evacuation")
    assert row.accepted_by == admin and "supplementary" in row.statement
    assert AuditLog.objects.filter(action="module.acknowledged").count() == 1
    modules.acknowledge(event, "evacuation", user=admin)  # once per event
    assert AuditLog.objects.filter(action="module.acknowledged").count() == 1
    html = admin_client.get(URL).content.decode()
    assert "Whole event" in html
    assert admin_client.post("/e/demo/settings/modules/screens/acknowledge/", {"accept": "on"}).status_code == 404
    with pytest.raises(ValueError):
        modules.acknowledge(event, "screens")


def test_people_who_may_not_accept(client, event, member):
    login_2fa(client, member)
    html = client.get(URL).content.decode()
    assert "An organiser of this event must accept" in html
    r = client.post("/e/demo/settings/modules/evacuation/acknowledge/", {"accept": "on"})
    assert r.status_code == 403


def test_switching_on_needs_the_statement(admin_client, event):
    modules.set_instance("evacuation", False)
    html = admin_client.get("/e/demo/settings/modules/").content.decode()
    assert "Statement to accept" in html and check_html(html) == []
    modules.set_instance("evacuation", True)
    r = admin_client.post("/e/demo/settings/modules/", {"key": "evacuation", "value": "on"}, follow=True)
    assert "tick the box" in r.content.decode() and modules.acknowledgement_needed("evacuation", event)
    admin_client.post("/e/demo/settings/modules/", {"key": "evacuation", "value": "on", "accept": "on"})
    assert not modules.acknowledgement_needed("evacuation", event)
    assert modules.is_enabled("evacuation", event)
    admin_client.post("/e/demo/settings/modules/", {"key": "evacuation", "value": "off"})  # off needs nothing
    from apps.events.models import Event

    assert not modules.is_enabled("evacuation", Event.objects.get(pk=event.pk))


def test_settings_page_shows_statement_and_status(admin_client, event, admin):
    url = "/e/demo/settings/s/evacuation/"
    html = admin_client.get(url).content.decode()
    assert "Safety statement" in html and "I have read this statement" in html and check_html(html) == []
    modules.acknowledge(event, "evacuation", user=admin)
    html = admin_client.get(url).content.decode()
    assert "accepted" in html and str(admin) in html


def test_api_and_bridge_refuse_before_acceptance(client, event, admin, zones):
    _t, raw = ServiceToken.issue(name="r", owner=admin, event=event, scopes=["evacuation:write"],
                                 created_with_2fa=True)
    r = client.get("/api/v1/events/demo/evacuation/", HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert r.status_code == 403 and "safety statement" in r.json()["detail"]
    b, token = bridges.create(event, "Panel", actor=admin)
    r = Client().post("/bridge/v1/heartbeat", data=json.dumps({}), content_type="application/json",
                      HTTP_AUTHORIZATION=f"Bearer {token}")
    assert r.status_code == 409
    modules.acknowledge(event, "evacuation", user=admin)
    assert client.get("/api/v1/events/demo/evacuation/", HTTP_AUTHORIZATION=f"Bearer {raw}").status_code == 200


def test_wizard_can_switch_it_on_with_the_statement(client, db, venue):
    from apps.accounts.models import User
    from apps.events.models import Event

    admin = User.objects.create_superuser(email="root@example.org", password="pw-123456789")
    login_2fa(client, admin)
    html = client.get("/setup/?step=event").content.decode()
    assert "Use the Evacuation module in this event" in html and "DIN 14675" in html
    client.post("/setup/?step=event", {"name": "Camp", "slug": "camp", "timezone": "UTC", "use_evacuation": "on"})
    ev = Event.objects.get(slug="camp")
    assert modules.is_enabled("evacuation", ev) and not modules.acknowledgement_needed("evacuation", ev)
    client.post("/setup/?step=event", {"name": "Two", "slug": "two", "timezone": "UTC"})
    assert modules.acknowledgement_needed("evacuation", Event.objects.get(slug="two"))
