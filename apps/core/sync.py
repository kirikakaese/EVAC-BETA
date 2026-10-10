# SPDX-License-Identifier: AGPL-3.0-or-later
"""Module switches and settings for venue nodes (ADR-0036). Instance-level settings travel too (the node runs the
event like central would), except the node's own ``general`` settings."""
from __future__ import annotations

from typing import Any

from django.apps import apps
from django.db.models import Q

from .plugins import SyncModel, SyncSpec

#: instance-level namespaces that belong to the node itself
NODE_LOCAL_NAMESPACES = ("general",)


def _settings(event: Any) -> Any:
    from .models import SettingValue

    ids = [str(event.pk)]
    venue_ids = [str(v) for v in event.venues.values_list("pk", flat=True)]
    screen_ids: list[str] = []
    group_ids: list[str] = []
    if apps.is_installed("apps.screens"):
        from apps.screens.models import Screen, ScreenGroup

        screen_ids = [str(s) for s in Screen.objects.filter(event=event).values_list("pk", flat=True)]
        group_ids = [str(g) for g in ScreenGroup.objects.filter(event=event).values_list("pk", flat=True)]
    return SettingValue.objects.filter(
        (Q(level="instance") & ~Q(namespace__in=NODE_LOCAL_NAMESPACES)) | Q(level="event", scope_id__in=ids)
        | Q(level="venue", scope_id__in=venue_ids) | Q(level="screen", scope_id__in=screen_ids)
        | Q(level="screen_group", scope_id__in=group_ids))


def spec() -> SyncSpec:
    from .models import EventModuleState, ModuleAcknowledgement, ModuleState

    return SyncSpec(module="core", order=30, models=(
        SyncModel("core.ModuleState", lambda e: ModuleState.objects.all(), natural_key=("key",),
                  delete_missing=False),
        SyncModel("core.EventModuleState", lambda e: EventModuleState.objects.filter(event=e),
                  natural_key=("event", "key")),
        SyncModel("core.ModuleAcknowledgement", lambda e: ModuleAcknowledgement.objects.filter(event=e),
                  natural_key=("event", "key")),
        SyncModel("core.SettingValue", _settings, natural_key=("namespace", "level", "scope_id"),
                  delete_missing=False),
    ))
