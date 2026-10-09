# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task

from . import services


@shared_task(name="apps.widgets.tasks.fetch_due")
def fetch_due() -> int:
    return services.fetch_due()


@shared_task(name="apps.widgets.tasks.fetch_feed")
def fetch_feed(feed_id: str) -> bool:
    from .models import Feed

    feed = Feed.objects.select_related("event").filter(pk=feed_id).first()
    return services.fetch_feed(feed) if feed is not None else False
