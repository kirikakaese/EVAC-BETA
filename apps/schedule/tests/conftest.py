# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt

import pytest
from django.utils import timezone

from apps.schedule import services
from apps.schedule.models import Session, Stage, Track

NOW = timezone.now().replace(second=0, microsecond=0)


def at(minutes: int) -> dt.datetime:
    return NOW + dt.timedelta(minutes=minutes)


@pytest.fixture
def stages(event):
    from apps.venues.models import Room

    hall = Room.objects.get(name="Hall A")
    return {"main": Stage.objects.create(event=event, name="Main stage", room=hall, order=0),
            "ws": Stage.objects.create(event=event, name="Workshop", order=1)}


@pytest.fixture
def talk(event, stages, admin):
    track = Track.objects.create(event=event, name="Security", colour="#2563eb")
    return services.save_session(Session(event=event, title="Opening", stage=stages["main"], track=track,
                                         starts_at=at(-15), ends_at=at(30)), actor=admin)


@pytest.fixture
def later(event, stages, admin):
    return services.save_session(Session(event=event, title="Lightning talks", stage=stages["main"],
                                         starts_at=at(45), ends_at=at(90)), actor=admin)


def imported(ext, title, start, end, **kw):
    return services.Imported(external_id=ext, title=title, starts_at=start, ends_at=end, **kw)
