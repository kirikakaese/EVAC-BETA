# SPDX-License-Identifier: AGPL-3.0-or-later
"""Program templates for the template gallery (ADR-0046): stage screen and day overview."""
from __future__ import annotations

from typing import Any

HEADING = {"fontFamily": "token:heading", "fontWeight": 800}


def _el(id_: str, type_: str, frame: tuple[float, float, float, float], props: dict[str, Any],
        **style: Any) -> dict[str, Any]:
    x, y, w, h = frame
    return {"id": id_, "type": type_, "name": id_.replace("-", " ").capitalize(),
            "frame": {"x": x, "y": y, "w": w, "h": h}, "style": style, "props": props}


def stage() -> dict[str, Any]:
    """The room's own sessions: now and next (the screen's room, else all stages)."""
    return {"format": 1, "width": 1920, "height": 1080, "background": {"color": "token:background"}, "elements": [
        _el("room", "text", (5, 5, 62, 12), {"text": "{{ screen.room }}", "autofit": True}, fontSize=7,
            color="token:accent", **HEADING),
        _el("clock", "clock", (70, 5, 25, 12), {"format": "HH:mm"}, fontSize=7, textAlign="right",
            tabularNumbers=True),
        _el("program", "program", (5, 22, 90, 72), {"view": "now_next", "stage": ""}, fontSize=4,
            background="token:surface", radius=2, padding=3),
    ]}


def day() -> dict[str, Any]:
    """Today's sessions with live changes beside them."""
    return {"format": 1, "width": 1920, "height": 1080, "background": {"color": "token:background"}, "elements": [
        _el("title", "text", (4, 4, 60, 10), {"text": "Today at {{ event.name }}", "autofit": True}, fontSize=6,
            **HEADING),
        _el("clock", "clock", (72, 4, 24, 10), {"format": "HH:mm"}, fontSize=6, textAlign="right",
            tabularNumbers=True),
        _el("day", "program", (4, 18, 60, 78), {"view": "day", "stage": "", "count": 10}, fontSize=3),
        _el("changes", "program", (67, 18, 29, 78), {"view": "changes", "title": "Changes"}, fontSize=3,
            background="token:surface", radius=2, padding=2),
    ]}
