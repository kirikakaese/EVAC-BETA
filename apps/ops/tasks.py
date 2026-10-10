# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task(name="apps.ops.tasks.escalate_due")
def escalate_due() -> int:
    from . import services

    return services.escalate_due()
