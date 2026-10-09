# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task

from . import services


@shared_task(name="apps.screens.tasks.sweep_health")
def sweep_health() -> int:
    return services.sweep_health()


@shared_task(name="apps.screens.tasks.purge_pairing_requests")
def purge_pairing_requests() -> int:
    return services.purge_pairing_requests()
