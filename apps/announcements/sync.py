# SPDX-License-Identifier: AGPL-3.0-or-later
"""Announcement levels and templates for venue nodes; announcements themselves (including drafts written on
site) belong to the node during a checkout (ADR-0036)."""
from __future__ import annotations

from typing import Any

from apps.core.plugins import SyncModel, SyncSpec


def _speech(a: Any) -> list[tuple[str, str]]:
    from . import tts

    return [(str(tts.path_of(a.speech_file)), "")] if a.speech_file else []


def spec() -> SyncSpec:
    from .models import Announcement, Delivery, Level, Template

    return SyncSpec(module="announcements", order=130, models=(
        SyncModel("announcements.Level", lambda e: Level.objects.filter(event=e)),
        SyncModel("announcements.Template", lambda e: Template.objects.filter(event=e)),
        SyncModel("announcements.Announcement", lambda e: Announcement.objects.filter(event=e), live=True,
                  files=_speech),
        SyncModel("announcements.Delivery", lambda e: Delivery.objects.filter(announcement__event=e), live=True),
    ))
