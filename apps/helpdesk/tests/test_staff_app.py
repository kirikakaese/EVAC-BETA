# SPDX-License-Identifier: AGPL-3.0-or-later
"""Full staff PWA (roadmap 9.1): found items from the staff page, offline replay, sync and scan controls."""
import datetime as dt

import pytest
from django.utils import timezone

from apps.core.a11y import audit_url
from apps.helpdesk import services
from apps.helpdesk.models import LostFound
from conftest import login_2fa

pytestmark = pytest.mark.django_db


def test_quick_found_is_idempotent_and_keeps_the_written_time(event, admin):
    written = timezone.now() - dt.timedelta(minutes=40)
    a = services.quick_found(event, what=" Blue umbrella ", where="Gate 2", actor=admin, client_id="c-1", at=written)
    b = services.quick_found(event, what="Blue umbrella", where="Gate 2", actor=admin, client_id="c-1", at=written)
    assert a.pk == b.pk and LostFound.objects.filter(event=event).count() == 1
    assert a.kind == "found" and a.what == "Blue umbrella" and a.reference == "F-0001"
    assert abs((a.when - written).total_seconds()) < 1
    future = services.quick_found(event, what="Phone", actor=admin, at=timezone.now() + dt.timedelta(hours=3))
    assert future.when <= timezone.now()
    old = services.quick_found(event, what="Hat", actor=admin, at=timezone.now() - dt.timedelta(days=3))
    assert old.when > timezone.now() - dt.timedelta(minutes=1)  # too far back: now


def test_staff_page_quick_form_and_replay(client, admin, event):
    login_2fa(client, admin)
    page = client.get("/e/demo/staff/").content.decode()
    assert 'action="/e/demo/helpdesk/lost-found/quick/"' in page and "data-offline" in page
    assert "data-scan" in page and "data-sync-global" in page
    body = {"what": "Keys", "where": "Bar", "client_id": "abc", "written_at": timezone.now().isoformat(),
            "next": "/e/demo/staff/"}
    r = client.post("/e/demo/helpdesk/lost-found/quick/", body)
    assert r.status_code == 302 and r["Location"] == "/e/demo/staff/"
    client.post("/e/demo/helpdesk/lost-found/quick/", body, HTTP_X_EVAC_QUEUED="1")  # replay from the queue
    assert LostFound.objects.filter(event=event, what="Keys").count() == 1
    r = client.post("/e/demo/helpdesk/lost-found/quick/", {"what": " ", "next": "https://evil.example/"})
    assert r.status_code == 302 and r["Location"] == "/e/demo/helpdesk/lost-found/"  # refused, no open redirect
    assert audit_url(client, "/e/demo/staff/") == []


def test_quick_found_needs_manage_permission(client, user, event):
    from apps.events import services as event_services
    from apps.events.models import Role

    event_services.assign_role(event, user, Role.objects.get(event=event, key="viewer"))
    login_2fa(client, user)
    r = client.post("/e/demo/helpdesk/lost-found/quick/", {"what": "Keys"})
    assert r.status_code in (403, 404) and not LostFound.objects.exists()
