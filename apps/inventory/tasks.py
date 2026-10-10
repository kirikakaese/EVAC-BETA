# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task(name="apps.inventory.tasks.remind_overdue")
def remind_overdue() -> int:
    from . import services

    return services.remind_overdue()
