# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evacuation actions central forwards to the venue node holding the event (ADR-0036). Central checked the
person's permissions (with their two-factor session); the node runs the action as that person, audit-logged."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import acks, machine, services, triggers
from .models import EvacRequest


def _zone(event: Any, zone_id: Any) -> Any:
    return services.zones_of(event).filter(pk=zone_id).first() if zone_id else None


def trigger(event: Any, payload: Mapping[str, Any], actor: Any) -> dict[str, Any]:
    out = triggers.trigger(event, str(payload["state"]), source=str(payload.get("source") or "web"),
                           zone=_zone(event, payload.get("zone")), drill=bool(payload.get("drill")), actor=actor,
                           reason=str(payload.get("reason") or ""), key=str(payload.get("key") or ""),
                           clear_zones=payload.get("clear_zones"), check_perms=False,
                           execute=bool(payload.get("execute")))
    return {"result": out.result, "request": str(out.request.pk) if out.request else None}


def decide(event: Any, payload: Mapping[str, Any], actor: Any) -> dict[str, Any]:
    req = EvacRequest.objects.filter(event=event, pk=payload.get("request")).first()
    if req is None:
        raise machine.Refused("unknown", "Unknown request.")
    if payload.get("verdict") == "confirm":
        triggers.confirm(req, actor=actor, request=_trusted())
        return {"result": "confirmed"}
    triggers.reject(req, actor=actor, request=_trusted())
    return {"result": "rejected"}


def block(event: Any, payload: Mapping[str, Any], actor: Any) -> dict[str, Any]:
    point = services.points_of(event).filter(pk=payload.get("point")).first()
    if point is None:
        raise machine.Refused("point", "Unknown point.")
    changed = services.set_blocked(event, point, bool(payload.get("blocked")), actor=actor,
                                   reason=str(payload.get("reason") or ""), source=str(payload.get("source") or "web"),
                                   check_perms=False)
    return {"result": "changed" if changed else "unchanged"}


def answer(event: Any, payload: Mapping[str, Any], actor: Any) -> dict[str, Any]:
    acks.staff_ack(event, actor, str(payload.get("kind")), zone=_zone(event, payload.get("zone")),
                   note=str(payload.get("note") or ""))
    return {"result": "recorded"}


class _Trusted:
    """A stand-in request for decisions central already authorised: permission checks pass for the actor."""

    trusted_node_action = True


def _trusted() -> Any:
    return _Trusted()


ACTIONS = {"evacuation.trigger": trigger, "evacuation.decide": decide, "evacuation.block": block,
           "evacuation.answer": answer}
