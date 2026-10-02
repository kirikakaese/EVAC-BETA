# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task(name="apps.events.tasks.apply_scheduled_transitions")
def apply_scheduled_transitions() -> int:
    from .services import apply_due_transitions

    return apply_due_transitions()
