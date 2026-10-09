# SPDX-License-Identifier: AGPL-3.0-or-later
"""The stored layout format (version 1), shared by the editor, the renderer and the API.

Positions and sizes are percentages of the canvas; font sizes, radii and padding are percentages of the
canvas height. The renderer draws into a container with ``container-type: size``, so the same layout looks
identical at every resolution (and in the editor preview). Colours are ``#rrggbb`` or theme tokens
(``token:primary``), fonts are ``token:body`` / ``token:heading`` or a font family id.

Text may contain template expressions (``{{ event.name|upper }}``, ``{% if screen.zone %}…{% endif %}``),
evaluated by the renderer; :func:`validate` only checks the structure, sizes and references.
"""
from __future__ import annotations

import uuid
from typing import Any

import jsonschema

FORMAT = 1
MAX_ELEMENTS = 300
COLOR = {"type": "string", "pattern": r"^(#[0-9a-fA-F]{6}|token:[a-z]+|transparent|)$"}
PCT = {"type": "number", "minimum": -100, "maximum": 200}
UUID = {"type": "string", "pattern": r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?$"}
TEXT = {"type": "string", "maxLength": 5000}

ELEMENT_TYPES = {
    "text": {"text": TEXT, "autofit": {"type": "boolean"}, "clamp": {"type": "integer", "minimum": 0, "maximum": 50},
             "marquee": {"type": "boolean"}},
    "richtext": {"text": TEXT},
    "image": {"asset": UUID, "fit": {"enum": ["cover", "contain", "fill"]},
              "alt": {"type": "string", "maxLength": 300}},
    "slideshow": {"assets": {"type": "array", "items": UUID, "maxItems": 100},
                  "interval": {"type": "number", "minimum": 1, "maximum": 3600},
                  "fit": {"enum": ["cover", "contain", "fill"]}},
    "video": {"asset": UUID, "loop": {"type": "boolean"}, "muted": {"type": "boolean"},
              "fit": {"enum": ["cover", "contain", "fill"]}},
    "audio": {"asset": UUID, "loop": {"type": "boolean"}},
    "shape": {"shape": {"enum": ["rect", "ellipse", "line"]}},
    "qr": {"text": {"type": "string", "maxLength": 1000}},
    "clock": {"format": {"enum": ["HH:mm", "HH:mm:ss", "h:mm a"]}, "timezone": {"type": "string", "maxLength": 64}},
    "countdown": {"target": {"type": "string", "maxLength": 200}, "finished": {"type": "string", "maxLength": 300},
                  "format": {"enum": ["auto", "hms", "ms", "days"]}},
    "date": {"format": {"enum": ["long", "short", "weekday", "iso"]}, "timezone": {"type": "string", "maxLength": 64}},
}

STYLE = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "color": COLOR, "background": COLOR, "borderColor": COLOR,
        "borderWidth": {"type": "number", "minimum": 0, "maximum": 20},
        "radius": {"type": "number", "minimum": 0, "maximum": 50},
        "padding": {"type": "number", "minimum": 0, "maximum": 50},
        "opacity": {"type": "number", "minimum": 0, "maximum": 1},
        "fontFamily": {"type": "string", "maxLength": 64},
        "fontSize": {"type": "number", "minimum": 0.5, "maximum": 100},
        "fontWeight": {"type": "integer", "minimum": 100, "maximum": 900},
        "fontStyle": {"enum": ["normal", "italic"]},
        "textAlign": {"enum": ["left", "center", "right", "justify"]},
        "verticalAlign": {"enum": ["top", "middle", "bottom"]},
        "lineHeight": {"type": "number", "minimum": 0.5, "maximum": 4},
        "letterSpacing": {"type": "number", "minimum": -0.5, "maximum": 2},
        "textTransform": {"enum": ["none", "uppercase", "lowercase", "capitalize"]},
        "tabularNumbers": {"type": "boolean"},
        "shadow": {"type": "boolean"},
    },
}


def _element_schema(kind: str) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False, "required": ["id", "type", "frame"],
        "properties": {
            "id": {"type": "string", "pattern": r"^[A-Za-z0-9_-]{1,40}$"},
            "type": {"const": kind},
            "name": {"type": "string", "maxLength": 100},
            "frame": {"type": "object", "additionalProperties": False, "required": ["x", "y", "w", "h"],
                      "properties": {"x": PCT, "y": PCT, "w": {"type": "number", "minimum": 0, "maximum": 300},
                                     "h": {"type": "number", "minimum": 0, "maximum": 300},
                                     "rotate": {"type": "number", "minimum": -360, "maximum": 360}}},
            "style": STYLE,
            "props": {"type": "object", "additionalProperties": False, "properties": ELEMENT_TYPES[kind]},
            "visible_if": {"type": "string", "maxLength": 300},
            "animation": {"type": "object", "additionalProperties": False, "properties": {
                "enter": {"enum": ["none", "fade", "slide-up", "slide-left", "zoom"]},
                "duration": {"type": "integer", "minimum": 0, "maximum": 10000},
                "delay": {"type": "integer", "minimum": 0, "maximum": 60000}}},
            "locked": {"type": "boolean"},
            "hidden": {"type": "boolean"},
        },
    }


SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["format", "width", "height", "elements"],
    "properties": {
        "format": {"const": FORMAT},
        "width": {"type": "integer", "minimum": 64, "maximum": 16384},
        "height": {"type": "integer", "minimum": 64, "maximum": 16384},
        "background": {"type": "object", "additionalProperties": False,
                       "properties": {"color": COLOR, "asset": UUID, "fit": {"enum": ["cover", "contain"]}}},
        "duration": {"type": "number", "minimum": 1, "maximum": 86400},
        "elements": {"type": "array", "maxItems": MAX_ELEMENTS,
                     "items": {"oneOf": [_element_schema(k) for k in ELEMENT_TYPES]}},
    },
}

PRESETS = {
    "1920x1080": (1920, 1080), "1080x1920": (1080, 1920), "3840x2160": (3840, 2160), "1280x720": (1280, 720),
    "1024x768": (1024, 768), "3840x1080": (3840, 1080), "1920x480": (1920, 480),
}


def empty(width: int = 1920, height: int = 1080) -> dict[str, Any]:
    return {"format": FORMAT, "width": width, "height": height, "elements": []}


def starter(width: int = 1920, height: int = 1080) -> dict[str, Any]:
    """A friendly first layout: event name, clock and a text block."""
    return {"format": FORMAT, "width": width, "height": height, "elements": [
        {"id": "title", "type": "text", "name": "Event name", "frame": {"x": 6, "y": 8, "w": 60, "h": 14},
         "style": {"fontFamily": "token:heading", "fontSize": 9, "fontWeight": 700, "color": "token:accent"},
         "props": {"text": "{{ event.name }}", "autofit": True}},
        {"id": "clock", "type": "clock", "name": "Clock", "frame": {"x": 70, "y": 8, "w": 24, "h": 14},
         "style": {"fontSize": 9, "textAlign": "right", "tabularNumbers": True}, "props": {"format": "HH:mm"}},
        {"id": "body", "type": "text", "name": "Message", "frame": {"x": 6, "y": 32, "w": 88, "h": 50},
         "style": {"fontSize": 6, "background": "token:surface", "radius": 2, "padding": 3, "shadow": True},
         "props": {"text": "Welcome! Edit this text in the layout editor.", "autofit": True}},
    ]}


def welcome(width: int = 1920, height: int = 1080) -> dict[str, Any]:
    """The slide a freshly paired screen shows when its event has no layouts yet (setup wizard, 1.5.4)."""
    center = {"textAlign": "center"}
    return {"format": FORMAT, "width": width, "height": height, "background": {"color": "token:background"},
            "elements": [
        {"id": "kicker", "type": "text", "name": "Kicker", "frame": {"x": 6, "y": 16, "w": 88, "h": 8},
         "style": {**center, "fontSize": 4.5, "fontWeight": 700, "color": "token:accent", "letterSpacing": 0.15,
                   "textTransform": "uppercase"}, "props": {"text": "Welcome to", "autofit": True}},
        {"id": "title", "type": "text", "name": "Event name", "frame": {"x": 6, "y": 25, "w": 88, "h": 22},
         "style": {**center, "fontFamily": "token:heading", "fontSize": 13, "fontWeight": 800},
         "props": {"text": "{{ event.name }}", "autofit": True, "clamp": 2}},
        {"id": "ready", "type": "text", "name": "Screen", "frame": {"x": 6, "y": 52, "w": 88, "h": 8},
         "style": {**center, "fontSize": 4, "color": "token:muted"},
         "props": {"text": "{{ screen.name }} is ready.", "autofit": True}},
        {"id": "hint", "type": "text", "name": "Hint", "frame": {"x": 12, "y": 61, "w": 76, "h": 10},
         "style": {**center, "fontSize": 3, "color": "token:muted"},
         "props": {"text": "Design slides under Design & assets → Layouts, and choose what plays under Playback.",
                   "autofit": True}},
        {"id": "clock", "type": "clock", "name": "Clock", "frame": {"x": 35, "y": 76, "w": 30, "h": 14},
         "style": {**center, "fontSize": 10, "tabularNumbers": True}, "props": {"format": "HH:mm"}},
    ]}


def validate(data: Any) -> list[str]:
    errors = []
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))[:20]:
        path = "/".join(str(p) for p in err.absolute_path) or "layout"
        errors.append(f"{path}: {err.message[:200]}")
    if not errors:
        ids = [e["id"] for e in data["elements"]]
        if len(ids) != len(set(ids)):
            errors.append("elements: element ids must be unique")
    return errors


def asset_ids(data: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    bg = (data.get("background") or {}).get("asset")
    if bg:
        out.add(bg)
    for el in data.get("elements", []):
        props = el.get("props") or {}
        if props.get("asset"):
            out.add(props["asset"])
        out.update(a for a in props.get("assets", []) if a)
    return out


def font_ids(data: dict[str, Any]) -> set[str]:
    return {f for el in data.get("elements", []) if (f := (el.get("style") or {}).get("fontFamily"))
            and not f.startswith("token:") and _is_uuid(f)}


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return True


def summary_diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[str]]:
    """Which elements were added, removed or changed between two versions (for the version list)."""
    a = {e["id"]: e for e in (old or {}).get("elements", [])}
    b = {e["id"]: e for e in (new or {}).get("elements", [])}

    def label(e):
        return e.get("name") or f"{e['type']} {e['id']}"

    return {
        "added": [label(b[i]) for i in b if i not in a],
        "removed": [label(a[i]) for i in a if i not in b],
        "changed": [label(b[i]) for i in b if i in a and a[i] != b[i]],
        "canvas": [k for k in ("width", "height", "background", "duration") if (old or {}).get(k) != new.get(k)],
    }


