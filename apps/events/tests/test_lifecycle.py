# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt
import json

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import AuditLog, EventModuleState, SettingValue
from apps.events import services
from apps.events.models import Event, ScheduledTransition
from apps.events.tasks import apply_scheduled_transitions


@pytest.mark.django_db
def test_transitions(event, admin):
    assert event.state == "draft"
    with pytest.raises(ValidationError):
        event.transition("live", user=admin)
    for target in ("setup", "live", "teardown", "archived", "teardown"):
        event.transition(target, user=admin)
    assert AuditLog.objects.filter(action="event.state_changed").count() == 5


@pytest.mark.django_db
def test_scheduled_transitions(event, admin):
    now = timezone.now()
    ScheduledTransition.objects.create(event=event, target_state="setup", at=now - dt.timedelta(minutes=1))
    bad = ScheduledTransition.objects.create(event=event, target_state="archived", at=now - dt.timedelta(seconds=30))
    later = ScheduledTransition.objects.create(event=event, target_state="live", at=now + dt.timedelta(hours=1))
    assert apply_scheduled_transitions() == 1
    event.refresh_from_db()
    bad.refresh_from_db()
    later.refresh_from_db()
    assert event.state == "setup" and "cannot go" in bad.error and later.applied_at is None


@pytest.mark.django_db
def test_slug_and_dates_validation(admin):
    with pytest.raises(ValidationError):
        services.create_event(name="Bad", slug="admin", user=admin)
    with pytest.raises(ValidationError):
        services.create_event(name="Bad", user=admin, start_date=dt.date(2026, 2, 2), end_date=dt.date(2026, 1, 1))
    with pytest.raises(ValidationError):
        services.create_event(name="Bad", user=admin, timezone="Mars/Olympus")
    assert services.unique_slug("Demo Camp") == "demo-camp"


@pytest.mark.django_db
def test_clone_with_and_without_content(event, admin, member):
    EventModuleState.objects.create(event=event, key="venues", enabled=False)
    SettingValue.objects.create(namespace="general", level="event", scope_id=str(event.pk),
                                values={"retention_days": 7})
    plain = services.clone_event(event, name="Copy", user=admin)
    assert plain.venues.count() == 1 and plain.module_states.get(key="venues").enabled is False
    assert SettingValue.objects.get(level="event", scope_id=str(plain.pk)).values == {"retention_days": 7}
    assert not plain.memberships.filter(user=member).exists()
    assert plain.memberships.filter(user=admin).exists()
    full = services.clone_event(event, name="Full", slug="full", with_content=True, user=admin)
    assert full.memberships.filter(user=member).exists()


@pytest.mark.django_db
def test_export_import_roundtrip(event, admin, member, role, venue):
    from apps.venues.models import Zone

    north = Zone.objects.get(name="North")
    services.assign_role(event, member, role("crew"), scope_kind="zone", scope_id=str(north.pk))
    event.roles.create(key="stage", name="Stage crew", permissions=["venues.view"])
    data = json.loads(json.dumps(services.export_event(event), default=str))
    assert data["evac_export"] == 1 and data["plugins"]["venues"][0]["slug"] == "hall"
    data["members"].append({"email": "ghost@example.org", "roles": [{"role": "crew"}]})
    copy, report = services.import_event(data, slug="imported", user=admin)
    assert copy.slug == "imported" and copy.roles.filter(key="stage").exists()
    assert copy.venues.get() == venue  # shared venue reused by slug
    assert copy.memberships.filter(user=member).exists()
    assert any("ghost@example.org" in line for line in report)
    with pytest.raises(ValidationError):
        services.import_event({"nope": 1})


@pytest.mark.django_db
def test_import_creates_missing_venue(event, admin):
    data = json.loads(json.dumps(services.export_event(event), default=str))
    data["plugins"]["venues"][0]["slug"] = "brand-new"
    copy, _ = services.import_event(data, user=admin)
    v = copy.venues.get()
    assert v.slug == "brand-new" and v.rooms.count() == 2 and v.zones.count() == 2
    assert v.rooms.get(name="Hall A").zones.get().name == "North"


@pytest.mark.django_db
def test_visible_to(event, admin, member, other):
    assert list(Event.objects.visible_to(member)) == [event]
    assert list(Event.objects.visible_to(other)) == []
    assert Event.objects.visible_to(admin).count() == 1
