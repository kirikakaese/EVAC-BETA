# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extension configuration for venue nodes (ADR-0036): only extensions marked ``secrets_on_site`` (needed at the
venue, e.g. MQTT bridges) travel, with their secrets sealed for the node; all others stay on central."""
from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.core.plugins import SyncModel, SyncSpec
from apps.core.registry import registry


def _configs(event: Any) -> Any:
    from .models import ExtensionConfig

    keys = [k for k, s in registry.ensure_loaded().extensions.items() if s.secrets_on_site]
    return ExtensionConfig.objects.filter(Q(event=event) | Q(event__isnull=True), extension__in=keys)


def spec() -> SyncSpec:
    return SyncSpec(module="extensions", order=40, models=(
        SyncModel("extensions.ExtensionConfig", _configs,
                  secret_fields=("secrets_encrypted", "webhook_secret_encrypted"),
                  local_fields=("health", "last_check_at", "last_sync_at", "last_error")),
    ))
