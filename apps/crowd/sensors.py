# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sensor input (ADR-0040): the same reading over HTTP (``POST /api/v1/events/<slug>/occupancy/<id>/count/``) and
MQTT (``<prefix>/crowd/<event slug>/<sensor key>``).

A reading is one of ``{"delta": n}`` (people in minus out), ``{"in": a, "out": b}``, ``{"value": n}`` (the sensor
knows the occupancy) or, over MQTT, a bare number (the occupancy). ``"id"`` (optional) makes a repeated message
harmless.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.core.exceptions import ValidationError

from apps.core import modules

from . import services
from .models import Area

log = logging.getLogger("evac.crowd")


def parse(body: Any) -> tuple[str, int, str]:
    """``(kind, number, id)``: kind ``delta`` or ``value``. Raises ValidationError."""
    if isinstance(body, bool):
        raise ValidationError("not a reading")
    if isinstance(body, int | float):
        return "value", int(body), ""
    if not isinstance(body, dict):
        raise ValidationError("send {\"delta\": n}, {\"in\": a, \"out\": b} or {\"value\": n}")
    ident = str(body.get("id") or "")[:64]

    def num(key: str) -> int:
        v = body.get(key)
        if isinstance(v, bool) or not isinstance(v, int | float):
            raise ValidationError(f"{key} must be a number")
        return int(v)

    if "value" in body:
        return "value", num("value"), ident
    if "delta" in body:
        return "delta", num("delta"), ident
    if "in" in body or "out" in body:
        return "delta", (num("in") if "in" in body else 0) - (num("out") if "out" in body else 0), ident
    raise ValidationError("send {\"delta\": n}, {\"in\": a, \"out\": b} or {\"value\": n}")


def apply(area: Area, body: Any, *, source: str, device: str = "") -> Area:
    kind, n, ident = parse(body)
    if kind == "value":
        return services.set_value(area, n, source=source, device=device, client_id=ident)
    return services.count(area, n, source=source, device=device, client_id=ident)


def mqtt_handler(topic: str, payload: bytes) -> None:
    """``crowd/<event slug>/<sensor key>`` (``r.mqtt_topic``)."""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "crowd":
        return
    area = Area.objects.select_related("event").filter(event__slug=parts[1], sensor_key=parts[2]).first()
    if area is None or not modules.is_enabled(services.MODULE, area.event):
        log.warning("crowd: no area for MQTT topic %s", topic)
        return
    try:
        body = json.loads(payload or b"null")
        apply(area, body, source="mqtt", device=parts[2])
    except (ValueError, ValidationError) as exc:
        log.warning("crowd: bad reading on %s: %s", topic, exc)
