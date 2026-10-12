# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extensions for the heartbeat module's health monitor (ADR-0052): every enabled connection that applies (the
event's own or the instance-wide one) by its last connection test. An extension that registers a health check under
its own key (DIAL) reports itself and is left out here. Read-only: nothing is tested from here."""
from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.plugins import HealthItem
from apps.core.registry import registry

from . import services


def check(event: Any) -> list[HealthItem]:
    reg = registry.ensure_loaded()
    out = []
    for key, spec in sorted(reg.extensions.items()):
        if key in reg.health_checks:
            continue
        config = services.effective(key, event)
        if config is None:
            continue
        url = reverse("extensions:event_detail", args=[event.slug, key]) if event is not None else reverse(
            "extensions:instance_detail", args=[key])
        if config.health == config.Health.ERROR:
            out.append(HealthItem(key=key, label=spec.name, status="warn", url=url, since=config.last_check_at,
                                  detail=str(_("The last connection test failed: %(e)s") % {
                                      "e": (config.last_error or "?")[:300]})))
        elif config.health == config.Health.OK:
            out.append(HealthItem(key=key, label=spec.name, status="ok", url=url, since=config.last_check_at,
                                  detail=str(_("Connection test passed."))))
    return out
