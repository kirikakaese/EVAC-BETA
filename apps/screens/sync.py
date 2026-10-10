# SPDX-License-Identifier: AGPL-3.0-or-later
"""Screens and groups for venue nodes (ADR-0036). Screens pair with the node: pairing and health are the node's
own and never overwritten."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec

LOCAL = ("token_hash", "token_prefix", "paired_at", "paired_by", "revoked_at", "last_seen_at", "last_ip", "reported",
         "health_state", "screenshot_at", "screenshot_error", "logs", "logs_at")


def spec() -> SyncSpec:
    from .models import Screen, ScreenGroup

    return SyncSpec(module="screens", order=110, models=(
        SyncModel("screens.ScreenGroup", lambda e: ScreenGroup.objects.filter(event=e)),
        SyncModel("screens.Screen", lambda e: Screen.objects.filter(event=e), local_fields=LOCAL),
    ))
