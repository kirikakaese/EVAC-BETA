# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task(name="extensions.pretix.tasks.sync_due")
def sync_due() -> int:
    from . import importer

    return importer.sync_due()
