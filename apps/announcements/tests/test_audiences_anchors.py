# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audiences and announcements timed relative to anchors (ADR-0025)."""
import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken, User
from apps.announcements import services
from apps.announcements.models import Announcement
from apps.core.models import AuditLog, Notification
from apps.core.plugins import Anchor, TimeAnchorSpec
from apps.core.registry import registry
from apps.core.signals import anchor_moved
from apps.events import services as event_services
from conftest import login_2fa

from .test_announcements import ann, levels, run  # noqa: F401 - fixtures

NOW = timezone.now().replace(microsecond=0)


@pytest.fixture
def talks():
    """A fake anchor source (the program module will be the real one in phase 5)."""
    items = {"t1": Anchor(start=NOW + dt.timedelta(hours=2), end=NOW + dt.timedelta(hours=3), label="Opening talk"),
             "t2": Anchor(start=NOW + dt.timedelta(hours=5), label="Closing")}
    spec = TimeAnchorSpec(key="talks", title="Talk", choices=lambda event: [(k, a.label) for k, a in items.items()],
                          resolve=lambda event, ident: items.get(ident))
    sources = registry.ensure_loaded().anchor_sources
    sources["talks"] = spec
    yield items
    del sources["talks"]


@pytest.fixture
def crew(event, role):
    users = {}
    for key in ("helpdesk", "crew", "security"):
        u = User.objects.create_user(email=f"{key}@example.org", password=f"pw-{key}-123456")
        event_services.assign_role(event, u, role(key))
        users[key] = u
    return users


def test_role_audience_limits_staff_notifications(admin, event, levels, crew, role, run):  # noqa: F811
    choices = dict(services.audience_choices(event))
    crew_key = f"roles:{role('crew').pk}"
    assert choices[crew_key] == "Role: Crew" and len(choices) == event.roles.count()
    a = services.save_draft(ann(event, levels["important"], audiences=[crew_key, f"roles:{role('security').pk}"],
                                channels=[services.STAFF]), actor=admin)
    assert services.audience_labels(a) == ["Role: Crew", "Role: Security"]
    assert services.audience_members(a) == {crew["crew"], crew["security"]}
    run(services.submit, a, actor=admin)
    d = a.deliveries.get()
    assert d.recipients == 2
    notified = set(Notification.objects.filter(title__contains="Doors open").values_list("user__email", flat=True))
    assert notified == {"crew@example.org", "security@example.org"}
    # without audiences everybody who may see announcements is reached
    b = run(services.submit, services.save_draft(ann(event, levels["important"], title="All",
                                                     channels=[services.STAFF]), actor=admin), actor=admin)
    assert services.audience_members(b) is None and b.deliveries.get().recipients >= 4
    with pytest.raises(ValidationError, match="Unknown audience"):
        services.save_draft(ann(event, levels["info"], audiences=["roles:nope"]), actor=admin)
    with pytest.raises(ValidationError, match="staff notifications"):
        services.save_draft(ann(event, levels["info"], audiences=[crew_key], channels=[services.SCREENS]),
                            actor=admin)
    with pytest.raises(ValidationError, match="list"):
        services.save_draft(ann(event, levels["info"], audiences="roles"), actor=admin)
    assert services.audience_members(ann(event, levels["info"], audiences=["gone:1"])) == set()


def test_anchor_sets_and_follows_the_time(admin, event, levels, talks, run):  # noqa: F811
    assert dict(services.anchor_choices(event)) == {"talks:t1": "Talk: Opening talk", "talks:t2": "Talk: Closing"}
    a = ann(event, levels["important"], anchor="talks:t1", anchor_offset=-10,
            ends_at=NOW + dt.timedelta(minutes=30))
    a.starts_at = NOW
    a = services.save_draft(a, actor=admin)
    assert a.starts_at == NOW + dt.timedelta(hours=2, minutes=-10) and a.anchor_label == "Opening talk"
    assert a.ends_at - a.starts_at == dt.timedelta(minutes=30)  # the duration is kept
    assert services.anchor_text(a) == "10 min before the start of Opening talk"
    run(services.submit, a, actor=admin)
    a.refresh_from_db()
    assert a.status == "scheduled"

    talks["t1"] = Anchor(start=NOW + dt.timedelta(hours=4), label="Opening talk (moved)")
    anchor_moved.send(sender="talks", event=event, anchor_id="t1")
    a.refresh_from_db()
    assert a.starts_at == NOW + dt.timedelta(hours=4, minutes=-10) and a.anchor_label == "Opening talk (moved)"
    assert AuditLog.objects.filter(action="announcement.rescheduled").exists()
    assert anchor_moved.send(sender="talks", event=event, anchor_id="t1")[0][1] == 0  # unchanged: nothing to do

    # moved later without a signal: the scheduler checks before sending
    talks["t1"] = Anchor(start=NOW + dt.timedelta(hours=6), label="Opening talk")
    assert services.publish_due(now=NOW + dt.timedelta(hours=4)) == 0
    a.refresh_from_db()
    assert a.status == "scheduled" and a.starts_at == NOW + dt.timedelta(hours=6, minutes=-10)
    assert run(services.publish_due, now=NOW + dt.timedelta(hours=6)) == 1
    a.refresh_from_db()
    assert a.status == "live"


def test_anchor_end_edge_after_and_gone(admin, event, levels, talks):  # noqa: F811
    a = services.save_draft(ann(event, levels["info"], anchor="talks:t1", anchor_edge="end", anchor_offset=5),
                            actor=admin)
    assert a.starts_at == NOW + dt.timedelta(hours=3, minutes=5)
    assert services.anchor_text(a) == "5 min after the end of Opening talk"
    a.anchor_offset = 0
    assert services.anchor_text(a) == "at the end of Opening talk"
    no_end = services.save_draft(ann(event, levels["info"], anchor="talks:t2", anchor_edge="end"), actor=admin)
    assert no_end.starts_at == NOW + dt.timedelta(hours=5)  # falls back to the start
    assert services.anchor_text(ann(event, levels["info"])) == ""

    del talks["t1"]
    anchor_moved.send(sender="talks", event=event, anchor_id="t1")
    assert AuditLog.objects.filter(action="announcement.anchor_lost").exists()
    a.refresh_from_db()
    assert a.starts_at == NOW + dt.timedelta(hours=3, minutes=5)  # keeps its last time
    assert services._anchor_moved_later(a, NOW) is False  # gone: sent at the last known time
    for bad, message in [
        ({"anchor": "talks:t1"}, "no longer exists"),
        ({"anchor": "nope:1"}, "no longer exists"),
        ({"anchor": "talks:t2", "recurrence": "daily", "recurrence_until": NOW.date()}, "cannot repeat"),
        ({"anchor": "talks:t2", "anchor_offset": 99999}, "at most a week"),
    ]:
        with pytest.raises(ValidationError, match=message):
            services.save_draft(ann(event, levels["info"], **bad), actor=admin)


def test_compose_page_with_anchor_and_audience(client, admin, event, levels, talks, role, run):  # noqa: F811
    login_2fa(client, admin)
    page = client.get("/e/demo/announcements/new/")
    assert b"Relative to" in page.content and b"Only these people" in page.content
    crew_key = f"roles:{role('crew').pk}"
    data = {"level": levels["important"].pk, "title": "{{anchor}} starts soon", "body": "", "short": "",
            "channels": ["screens", "staff"], "all_screens": "on", "anchor": "talks:t1", "anchor_minutes": "15",
            "anchor_when": "before", "anchor_edge": "start", "audiences": [crew_key], "action": "send"}
    response = run(client.post, "/e/demo/announcements/new/", data)
    a = Announcement.objects.get()
    assert response.status_code == 302 and a.title == "Opening talk starts soon"
    assert a.anchor_offset == -15 and a.audiences == [crew_key] and a.status == "scheduled"
    detail = client.get(f"/e/demo/announcements/{a.pk}/").content
    assert b"15 min before the start of Opening talk" in detail and b"Role: Crew" in detail
    bad = client.post("/e/demo/announcements/new/", {**data, "recurrence": "daily",
                                                      "recurrence_until": NOW.date().isoformat()})
    assert "cannot repeat" in str(bad.context["form"].errors)


def test_compose_page_without_sources(client, admin, event, levels):  # noqa: F811
    login_2fa(client, admin)
    page = client.get("/e/demo/announcements/new/")
    assert b"Relative to" not in page.content and b"var_anchor" not in page.content


def test_api_fields(admin, event, levels, talks, role):  # noqa: F811
    _token, raw = ServiceToken.issue(name="ci", owner=admin, scopes=["announcements:write"], event=event)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    crew_key = f"roles:{role('crew').pk}"
    r = api.post("/api/v1/events/demo/announcements/", {"level": "info", "title": "Soon", "anchor": "talks:t2",
                                                         "anchor_offset": -5, "audiences": [crew_key],
                                                         "channels": ["screens", "staff"]},
                 format="json")
    assert r.status_code == 201, r.content
    assert r.json()["anchor_label"] == "Closing" and r.json()["audiences"] == [crew_key]
    assert r.json()["starts_at"].startswith((NOW + dt.timedelta(hours=5, minutes=-5)).astimezone(
        dt.UTC).strftime("%Y-%m-%dT%H:%M"))
    bad = api.post("/api/v1/events/demo/announcements/", {"level": "info", "title": "x", "audiences": "x"},
                   format="json")
    assert bad.status_code == 400
