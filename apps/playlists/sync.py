# SPDX-License-Identifier: AGPL-3.0-or-later
"""Playlists and schedules for venue nodes; live overrides belong to the node during a checkout (ADR-0036)."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def spec() -> SyncSpec:
    from .models import Override, Playlist, PlaylistItem, ScheduleRule

    return SyncSpec(module="playlists", order=120, models=(
        SyncModel("playlists.Playlist", lambda e: Playlist.objects.filter(event=e)),
        SyncModel("playlists.PlaylistItem", lambda e: PlaylistItem.objects.filter(playlist__event=e)),
        SyncModel("playlists.ScheduleRule", lambda e: ScheduleRule.objects.filter(event=e)),
        SyncModel("playlists.Override", lambda e: Override.objects.filter(event=e), live=True),
    ))
