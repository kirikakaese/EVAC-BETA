# SPDX-License-Identifier: AGPL-3.0-or-later
"""Design tokens of a theme: a flat JSON schema (so the settings form framework renders it with
"inherited" checkboxes) and the compilation to CSS custom properties (``--evac-…``)."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

PALETTE = [
    ("background", "Background", "#0b0d12", "#ffffff"),
    ("surface", "Surface (cards, panels)", "#161a22", "#f2f4f8"),
    ("text", "Text", "#f4f6fb", "#11151c"),
    ("muted", "Muted text", "#aab3c5", "#4d5668"),
    ("primary", "Primary", "#4f8cff", "#1d4ed8"),
    ("accent", "Accent", "#ffd400", "#b45309"),
    ("success", "Success", "#22c55e", "#15803d"),
    ("warning", "Warning", "#f59e0b", "#b45309"),
    ("danger", "Danger", "#ef4444", "#b91c1c"),
]

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def schema(fonts: list[tuple[str, str]] | None = None, images: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """The token schema; ``fonts`` and ``images`` are ``(value, label)`` choices of the event."""
    fonts = fonts or [("system", "System UI")]
    images = [("", "none"), *(images or [])]
    props: dict[str, Any] = {
        "mode": {"type": "string", "title": "Colour mode", "enum": ["dark", "light"],
                 "x-enum-labels": ["Dark", "Light"], "default": "dark"},
    }
    for key, label, dark, _light in PALETTE:
        props[f"dark_{key}"] = {"type": "string", "format": "color", "title": f"{label} (dark)", "default": dark}
    for key, label, _dark, light in PALETTE:
        props[f"light_{key}"] = {"type": "string", "format": "color", "title": f"{label} (light)", "default": light}
    font_values, font_labels = [f[0] for f in fonts], [f[1] for f in fonts]
    props.update({
        "font_body": {"type": "string", "title": "Body font", "enum": font_values, "x-enum-labels": font_labels,
                      "default": font_values[0]},
        "font_heading": {"type": "string", "title": "Heading font", "enum": font_values,
                         "x-enum-labels": font_labels, "default": font_values[0]},
        "font_size_base": {"type": "number", "title": "Base text size (% of screen height)", "minimum": 1,
                           "maximum": 20, "default": 3.2},
        "type_scale": {"type": "number", "title": "Type scale (heading size factor per level)", "minimum": 1,
                       "maximum": 2, "default": 1.25},
        "line_height": {"type": "number", "title": "Line height", "minimum": 0.8, "maximum": 2.5, "default": 1.3},
        "heading_weight": {"type": "integer", "title": "Heading weight", "minimum": 100, "maximum": 900,
                           "default": 700},
        "letter_spacing": {"type": "number", "title": "Letter spacing (em)", "minimum": -0.2, "maximum": 0.5,
                           "default": 0},
        "spacing": {"type": "number", "title": "Spacing unit (% of screen height)", "minimum": 0, "maximum": 10,
                    "default": 2},
        "radius": {"type": "number", "title": "Corner radius (% of screen height)", "minimum": 0, "maximum": 10,
                   "default": 1},
        "shadow": {"type": "string", "title": "Shadow", "enum": ["none", "soft", "strong"],
                   "x-enum-labels": ["None", "Soft", "Strong"], "default": "soft"},
        "background_type": {"type": "string", "title": "Background", "enum": ["color", "gradient", "image"],
                            "x-enum-labels": ["Colour", "Gradient", "Image"], "default": "color"},
        "gradient_from": {"type": "string", "format": "color", "title": "Gradient from", "default": "#0b0d12"},
        "gradient_to": {"type": "string", "format": "color", "title": "Gradient to", "default": "#1e293b"},
        "gradient_angle": {"type": "integer", "title": "Gradient angle (degrees)", "minimum": 0, "maximum": 360,
                           "default": 160},
        "background_image": {"type": "string", "title": "Background image", "enum": [v for v, _ in images],
                             "x-enum-labels": [label for _, label in images], "default": ""},
        "logo": {"type": "string", "title": "Logo", "enum": [v for v, _ in images],
                 "x-enum-labels": [label for _, label in images], "default": ""},
        "transition": {"type": "string", "title": "Slide transition", "enum": ["fade", "slide", "none"],
                       "x-enum-labels": ["Fade", "Slide", "None"], "default": "fade"},
        "transition_ms": {"type": "integer", "title": "Transition duration (ms)", "minimum": 0, "maximum": 5000,
                          "default": 600},
    })
    return {"type": "object", "properties": props}


SHADOWS = {"none": "none", "soft": "0 0.4vh 1.6vh rgba(0,0,0,.25)", "strong": "0 0.8vh 3vh rgba(0,0,0,.5)"}


def _font_stack(value: str, families: Mapping[str, str]) -> str:
    return families.get(value) or 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'


def css_variables(tok: Mapping[str, Any], *, families: Mapping[str, str] | None = None,
                  urls: Mapping[str, str] | None = None) -> dict[str, str]:
    """Resolved tokens -> ``{"--evac-color-primary": "#4f8cff", ...}``. ``families`` maps font values to CSS
    font stacks, ``urls`` maps asset ids to URLs (portal or player)."""
    families, urls = families or {}, urls or {}
    mode = "light" if tok.get("mode") == "light" else "dark"
    out: dict[str, str] = {}
    for key, *_ in PALETTE:
        value = str(tok.get(f"{mode}_{key}", ""))
        if HEX.match(value):
            out[f"--evac-color-{key}"] = value
    out["--evac-font-body"] = _font_stack(str(tok.get("font_body", "")), families)
    out["--evac-font-heading"] = _font_stack(str(tok.get("font_heading", "")), families)
    out["--evac-font-size"] = f"{float(tok.get('font_size_base', 3.2)):g}vh"
    out["--evac-type-scale"] = f"{float(tok.get('type_scale', 1.25)):g}"
    out["--evac-line-height"] = f"{float(tok.get('line_height', 1.3)):g}"
    out["--evac-heading-weight"] = str(int(tok.get("heading_weight", 700)))
    out["--evac-letter-spacing"] = f"{float(tok.get('letter_spacing', 0)):g}em"
    out["--evac-space"] = f"{float(tok.get('spacing', 2)):g}vh"
    out["--evac-radius"] = f"{float(tok.get('radius', 1)):g}vh"
    out["--evac-shadow"] = SHADOWS.get(str(tok.get("shadow")), SHADOWS["soft"])
    bg_type = tok.get("background_type", "color")
    background = out.get("--evac-color-background", "#000")
    if bg_type == "gradient" and HEX.match(str(tok.get("gradient_from", ""))) and HEX.match(
            str(tok.get("gradient_to", ""))):
        background = (f"linear-gradient({int(tok.get('gradient_angle', 160))}deg, {tok['gradient_from']}, "
                      f"{tok['gradient_to']})")
    elif bg_type == "image" and tok.get("background_image") in urls:
        background = f'{background} url("{urls[tok["background_image"]]}") center / cover no-repeat'
    out["--evac-background"] = background
    if tok.get("logo") in urls:
        out["--evac-logo"] = f'url("{urls[tok["logo"]]}")'
    out["--evac-transition"] = str(tok.get("transition", "fade"))
    out["--evac-transition-ms"] = f"{int(tok.get('transition_ms', 600))}ms"
    return out


def css_block(variables: Mapping[str, str], selector: str = ":root") -> str:
    body = "".join(f"{k}:{v};" for k, v in variables.items() if not re.search(r"[;{}<>\\]", v))
    return f"{selector}{{{body}}}"


def referenced_assets(tok: Mapping[str, Any]) -> set[str]:
    return {str(tok[k]) for k in ("background_image", "logo") if tok.get(k)}
