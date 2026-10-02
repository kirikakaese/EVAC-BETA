# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared pytest fixtures."""
import datetime as dt

import pyotp
import pytest
from django.core.cache import cache

from apps.accounts.models import User
from apps.accounts.twofactor import SESSION_KEY
from apps.events import services
from apps.venues.models import Building, Floor, Room, Venue, Zone


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def admin(db):
    return User.objects.create_superuser(email="root@example.org", password="pw-root-12345", display_name="Root")


@pytest.fixture
def user(db):
    return User.objects.create_user(email="alice@example.org", password="pw-alice-12345", display_name="Alice")


@pytest.fixture
def other(db):
    return User.objects.create_user(email="bob@example.org", password="pw-bob-123456", display_name="Bob")


@pytest.fixture
def venue(db):
    v = Venue.objects.create(slug="hall", name="Hall", timezone="Europe/Berlin")
    b = Building.objects.create(venue=v, name="Main")
    f = Floor.objects.create(building=b, name="Ground", level=0)
    north = Zone.objects.create(venue=v, name="North")
    south = Zone.objects.create(venue=v, name="South")
    r1 = Room.objects.create(venue=v, floor=f, name="Hall A", capacity=500)
    r1.zones.set([north])
    r2 = Room.objects.create(venue=v, floor=f, name="Hall B", capacity=300)
    r2.zones.set([south])
    return v


@pytest.fixture
def event(db, admin, venue):
    today = dt.date(2026, 7, 1)
    ev = services.create_event(name="Demo Camp", slug="demo", user=admin, timezone="Europe/Berlin",
                               start_date=today, end_date=today + dt.timedelta(days=3))
    ev.venues.add(venue)
    return ev


@pytest.fixture
def role(event):
    return lambda key: event.roles.get(key=key)


@pytest.fixture
def member(event, user, role):
    """``user`` with the built-in viewer role."""
    services.assign_role(event, user, role("viewer"))
    return user


@pytest.fixture
def orga(event, db, role):
    u = User.objects.create_user(email="orga@example.org", password="pw-orga-12345")
    services.assign_role(event, u, role("orga"))
    return u


def login_2fa(client, user):
    """Log ``user`` in with a two-factor verified session."""
    client.force_login(user)
    session = client.session
    session[SESSION_KEY] = "2026-01-01T00:00:00"
    session.save()
    return client


@pytest.fixture
def admin_client(client, admin):
    return login_2fa(client, admin)


def totp_now(device) -> str:
    return pyotp.TOTP(device.secret).now()
