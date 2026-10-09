# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task

from . import services


@shared_task(name="apps.announcements.tasks.publish_due")
def publish_due() -> int:
    return services.publish_due()
