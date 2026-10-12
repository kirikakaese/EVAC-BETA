# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task(name="apps.heartbeat.tasks.evaluate")
def evaluate() -> int:
    """Every 30 s: write the Celery pulse, evaluate the health checks and run due check-in escalations."""
    from apps.core import modules
    from apps.events.models import Event

    from . import checkin, checks, services

    checks.beat()
    n = services.evaluate_all()
    for event in Event.objects.exclude(state=Event.State.ARCHIVED):
        if modules.is_enabled(services.MODULE, event):
            n += checkin.escalate_due(event)
    return n
