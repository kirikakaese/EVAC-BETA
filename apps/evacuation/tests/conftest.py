# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.test import RequestFactory

from apps.accounts.twofactor import SESSION_KEY
from apps.core import modules, settings_store


@pytest.fixture(autouse=True)
def evacuation_on(db):
    modules.set_instance("evacuation", True)
    # most tests use zone states; the default model (staged) is tested on its own
    settings_store.save("evacuation", "instance", "", {"model": "zones"})


@pytest.fixture
def zones(venue):
    return {z.name: z for z in venue.zones.all()}


def tf(user):
    """A request of ``user`` in a two-factor verified session (alarm permissions are sensitive)."""
    request = RequestFactory().post("/")
    request.user = user
    request.session = {SESSION_KEY: "2026-01-01T00:00:00"}
    return request
