# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task(name="apps.content.tasks.process_asset")
def process_asset(asset_id: str) -> str:
    from . import services
    from .models import Asset

    asset = Asset.objects.filter(pk=asset_id).first()
    if asset is None:
        return "gone"
    return services.process(asset).status
