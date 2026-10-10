# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task
def process_due() -> int:
    """Escalate armed alarms, expire two-person requests, start scheduled drills (every 5 s)."""
    from . import triggers

    return triggers.process_due()
