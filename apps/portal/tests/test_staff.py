# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import pytest

from apps.accounts.models import User
from apps.announcements import services as ann
from apps.announcements.models import Announcement, Level
from apps.core import modules, realtime
from apps.core.a11y import audit_url
from apps.events import services as event_services
from conftest import login_2fa


@pytest.fixture
def helpdesk(event, role):
    u = User.objects.create_user(email="desk@example.org", password="pw-desk-123456")
    event_services.assign_role(event, u, role("helpdesk"))
    return u


def test_manifest_and_service_worker(client, db):
    data = json.loads(client.get("/manifest.webmanifest").content)
    assert data["start_url"] == "/staff/" and data["display"] == "standalone"
    assert {i["sizes"] for i in data["icons"]} == {"192x192", "512x512", "any"}
    sw = client.get("/sw.js")
    body = sw.content.decode()
    assert sw["Content-Type"] == "application/javascript" and sw["Service-Worker-Allowed"] == "/"
    assert "__VERSION__" not in body and "__SHELL__" not in body and '"/offline/"' in body
    assert "no-cache" in sw["Cache-Control"]
    assert client.get("/offline/").status_code == 200
    page = client.get("/offline/").content.decode()
    assert 'rel="manifest"' in page and 'name="theme-color"' in page


def test_staff_start_redirects(client, admin, event):
    assert client.get("/staff/")["Location"] == "/"
    login_2fa(client, admin)
    client.get("/e/demo/")  # remembers the current event
    assert client.get("/staff/")["Location"] == "/e/demo/staff/"


def test_staff_page_cards_and_approval(client, event, helpdesk, admin):
    ann.ensure_defaults(event)
    a = Announcement(event=event, level=Level.objects.get(event=event, key="important"), title="Bar closes",
                     channels=["staff"])
    ann.save_draft(a, actor=helpdesk)
    ann.submit(a, actor=helpdesk)
    assert a.status == "pending"
    # the author sees that it waits, but cannot approve it
    login_2fa(client, helpdesk)
    page = client.get("/e/demo/staff/").content.decode()
    assert "1 of your announcements waits for approval." in page and "Approve" not in page
    assert "Switch on notifications" in page and 'data-offline' not in page
    # an approver gets the buttons (forms queue offline) and returns to the staff page
    login_2fa(client, admin)
    page = client.get("/e/demo/staff/").content.decode()
    assert "Waiting for your approval" in page and "data-offline" in page and "Bar closes" in page
    r = client.post(f"/e/demo/announcements/{a.pk}/approve/", {"next": "/e/demo/staff/"})
    assert r["Location"] == "/e/demo/staff/"
    a.refresh_from_db()
    assert a.status == "live"
    page = client.get("/e/demo/staff/").content.decode()
    assert "On air" in page
    r = client.post(f"/e/demo/announcements/{a.pk}/cancel/", {"next": "https://evil.example.org/"})
    assert r["Location"] == f"/e/demo/announcements/{a.pk}/"


def test_staff_page_without_announcements(client, event, member, admin):
    login_2fa(client, admin)
    modules.set_event(event, "announcements", False, user=admin)
    page = client.get("/e/demo/staff/").content.decode()
    assert "This device" in page and "staff-announcements" not in page
    login_2fa(client, member)  # viewer: sees on-air announcements but cannot send
    modules.set_event(event, "announcements", None, user=admin)
    page = client.get("/e/demo/staff/").content.decode()
    assert "staff-announcements" in page and "New announcement" not in page


def test_emergency_goes_live_on_staff_pages(admin, event, django_capture_on_commit_callbacks):
    from django.test import RequestFactory

    from apps.accounts.twofactor import SESSION_KEY

    ann.ensure_defaults(event)
    request = RequestFactory().get("/")
    request.user, request.session = admin, {SESSION_KEY: "x"}
    a = Announcement(event=event, level=Level.objects.get(event=event, key="emergency"), title="Storm",
                     body="Leave the field", channels=["staff"])
    ann.save_draft(a, actor=admin)
    with django_capture_on_commit_callbacks(execute=True):
        ann.submit(a, actor=admin, request=request)
    msgs = [m for m in realtime.since(event.pk, 0) if m["type"] == "announcement.live"]
    assert msgs and msgs[-1]["data"]["alert"] is True and msgs[-1]["data"]["title"] == "Storm"


def test_staff_page_is_accessible(client, admin, event):
    login_2fa(client, admin)
    assert audit_url(client, "/e/demo/staff/") == []
    assert audit_url(client, "/offline/") == []
