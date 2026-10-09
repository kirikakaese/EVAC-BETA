# SPDX-License-Identifier: AGPL-3.0-or-later
"""Screens fetch their configuration again when settings that concern them change."""
from __future__ import annotations

from django.db import transaction

NAMESPACES = ("screens", "display", "general")


def affected_screens(level: str, scope_id: str):
    from .models import Screen, ScreenGroup

    qs = Screen.objects.paired()
    if level == "event":
        return qs.filter(event_id=scope_id)
    if level == "screen":
        return qs.filter(pk=scope_id)
    if level == "screen_group":
        group = ScreenGroup.objects.filter(pk=scope_id).first()
        return group.screens().filter(pk__in=qs.values("pk")) if group else qs.none()
    if level == "venue":
        return qs.filter(event__venues__pk=scope_id).distinct()
    return qs  # instance level: everyone


def settings_changed(sender, instance, **kwargs) -> None:
    if instance.namespace not in NAMESPACES:
        return
    level, scope_id = instance.level, instance.scope_id

    def notify():
        from . import channel

        for screen in affected_screens(level, scope_id):
            channel.send(screen, "config.changed", {})

    transaction.on_commit(notify)
