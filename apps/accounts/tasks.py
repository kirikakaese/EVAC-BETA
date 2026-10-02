# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt

from celery import shared_task
from django.utils import timezone


@shared_task(name="apps.accounts.tasks.purge_expired_invitations")
def purge_expired_invitations(days: int = 30) -> int:
    from apps.events.models import Invitation

    deleted, _ = Invitation.objects.filter(accepted_at__isnull=True,
                                           expires_at__lt=timezone.now() - dt.timedelta(days=days)).delete()
    return deleted
