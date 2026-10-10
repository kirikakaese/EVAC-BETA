# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evacuation for venue nodes (ADR-0036). Configuration (policies, drills, bridges, stage content, the alarm key)
comes from central; the state, its history, blocked points, requests and acknowledgements belong to the node
during a checkout. The alarm key's private half travels sealed; the node's message counter stays its own and is
handed back at check-in."""
from __future__ import annotations

from typing import Any

from apps.core.plugins import SyncModel, SyncSpec


def _speech(c: Any) -> list[tuple[str, str]]:
    from django.apps import apps

    if not c.speech_file or not apps.is_installed("apps.announcements"):
        return []
    from apps.announcements import tts

    return [(str(tts.path_of(c.speech_file)), "")]


def spec() -> SyncSpec:
    from .models import (
        BlockedPoint,
        Bridge,
        EvacPolicy,
        EvacRequest,
        EvacState,
        EventAlarm,
        LatencySample,
        ScheduledDrill,
        ScreenAck,
        StaffAck,
        StageContent,
        StateChange,
    )

    def ev(model: Any) -> Any:
        return lambda e: model.objects.filter(event=e)

    return SyncSpec(module="evacuation", order=150, models=(
        SyncModel("evacuation.EventAlarm", ev(EventAlarm), local_fields=("seq", "seq_at", "watchdog_seq"),
                  secret_fields=("private_key_encrypted",), delete_missing=False),
        SyncModel("evacuation.EvacPolicy", ev(EvacPolicy)),
        SyncModel("evacuation.ScheduledDrill", ev(ScheduledDrill), local_fields=("started_at",)),
        SyncModel("evacuation.Bridge", ev(Bridge),
                  local_fields=("status", "online", "last_seen", "last_ip", "transport")),
        SyncModel("evacuation.StageContent", ev(StageContent), files=_speech),
        SyncModel("evacuation.EvacState", ev(EvacState), live=True),
        SyncModel("evacuation.StateChange", ev(StateChange), live=True),
        SyncModel("evacuation.BlockedPoint", ev(BlockedPoint), live=True),
        SyncModel("evacuation.EvacRequest", ev(EvacRequest), live=True),
        SyncModel("evacuation.StaffAck", ev(StaffAck), live=True),
        SyncModel("evacuation.ScreenAck", ev(ScreenAck), live=True),
        SyncModel("evacuation.LatencySample", ev(LatencySample), live=True),
    ))
