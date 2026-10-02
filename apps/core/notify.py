# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-app notifications (the bell in the top bar)."""
from __future__ import annotations

from .models import Notification


def notify(users, title: str, *, body: str = "", url: str = "", level: str = "info", event=None) -> int:
    rows = [Notification(user=u, title=title[:200], body=body, url=url, level=level, event=event) for u in users]
    Notification.objects.bulk_create(rows)
    return len(rows)


def unread_count(user) -> int:
    if not getattr(user, "is_authenticated", False):
        return 0
    return Notification.objects.filter(user=user, read_at__isnull=True).count()
