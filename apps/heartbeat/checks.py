# SPDX-License-Identifier: AGPL-3.0-or-later
"""The heartbeat module's own check (the Celery pulse) and the data source of the screens' alive indicator."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.plugins import HealthItem

from .models import Pulse

#: the heartbeat task runs this often (``CELERY_BEAT_SCHEDULE["heartbeat-evaluate"]``)
TASK_SECONDS = 30
PULSE = "celery"
#: how often screens refresh the alive indicator's data source
ALIVE_TTL = 10


def beat(now: dt.datetime | None = None) -> None:
    Pulse.objects.update_or_create(key=PULSE, defaults={"at": now or timezone.now()})


def celery(event: Any) -> list[HealthItem]:
    """Worker and beat: the periodic heartbeat task writes a pulse; no recent pulse means one of them is down."""
    label = _("Background worker (Celery)")
    p = Pulse.objects.filter(key=PULSE).first()
    if p is None:
        return [HealthItem(key=PULSE, label=label, status="unknown",
                           detail=_("The heartbeat task has not run yet. Are the Celery worker and beat running?"))]
    age = (timezone.now() - p.at).total_seconds()
    if age <= 3 * TASK_SECONDS:
        return [HealthItem(key=PULSE, label=label, status="ok", detail=_("Worker and beat are running."), since=p.at)]
    minutes = max(1, int(age // 60))
    detail = _("No periodic task ran for %(m)s min: the worker or beat is down. Outbox deliveries, escalations and "
               "scheduled publishing wait until it is back.") % {"m": minutes}
    return [HealthItem(key=PULSE, label=label, status="warn" if age <= 600 else "down", detail=detail, since=p.at)]


def alive(event: Any) -> dict[str, Any]:
    """Payload of ``heartbeat.alive``: the server's time (changes with every fresh answer, so a screen notices when
    its refreshes stop reaching the server) and the event's time zone for the clock."""
    return {"server_time": timezone.now().isoformat(), "timezone": event.timezone, "ttl": ALIVE_TTL}
