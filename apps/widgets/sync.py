# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data feeds and custom widgets for venue nodes (ADR-0036); a feed's auth header travels sealed."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def spec() -> SyncSpec:
    from .models import CustomWidget, Feed

    return SyncSpec(module="widgets", order=140, models=(
        SyncModel("widgets.Feed", lambda e: Feed.objects.filter(event=e), secret_fields=("auth_header_encrypted",),
                  local_fields=("status", "error", "last_fetch_at", "last_success_at", "snapshot", "snapshot_hash",
                                "etag")),
        SyncModel("widgets.CustomWidget", lambda e: CustomWidget.objects.filter(event=e)),
    ))
