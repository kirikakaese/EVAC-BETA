# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task
def download(import_id: str) -> str:
    from . import services
    from .models import PackImport

    pi = PackImport.objects.filter(pk=import_id).first()
    if pi is None:
        return "gone"
    return services.download(pi).status


@shared_task
def cleanup() -> int:
    from . import services

    return services.cleanup()
