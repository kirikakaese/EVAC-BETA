# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from apps.core import settings_store


@pytest.fixture(autouse=True)
def zones_model(db):
    settings_store.save("evacuation", "instance", "", {"model": "zones"})


@pytest.fixture
def zones(venue):
    return {z.name: z for z in venue.zones.all()}
