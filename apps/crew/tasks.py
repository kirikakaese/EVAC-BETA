# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task(name="apps.crew.tasks.mark_no_shows")
def mark_no_shows() -> int:
    from . import services

    return services.mark_no_shows()
