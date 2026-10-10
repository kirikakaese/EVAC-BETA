# SPDX-License-Identifier: AGPL-3.0-or-later
"""Guardrails for evacuation layouts (brief §8.4, ADR-0033). Pure Python, mypy strict.

A layout used for an evacuation stage is checked on save and publish:

- **required elements**: a safety sign (pictogram) and a text; in the zones-and-routes model also a direction
  (an arrow sign, or the ``{{ evac.direction }}`` text). Missing ones are errors (publishing is blocked).
- **contrast** of every text against what is behind it: below 4.5:1 is an error, below 7:1 a warning (WCAG).
- **text size** for the viewing distance: letters must be at least 1/250 of the distance high (a common sign
  rule, about 4 mm per metre). Font sizes are a share of the canvas height, so the screen height matters.
  Below half the minimum is an error, below the minimum a warning.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: cap height is about 0.7 of the font size
CAP = 0.7
#: letter height per metre of viewing distance
LETTER_PER_M = 1 / 250
TEXT_TYPES = ("text", "richtext")
DIRECTION_VARS = ("evac.direction", "evac.arrow", "evac.target")


@dataclass(frozen=True)
class Finding:
    level: str  # error | warning
    code: str
    message: str
    element: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"level": self.level, "code": self.code, "message": self.message, "element": self.element}


def _hex(value: str) -> tuple[float, float, float] | None:
    if len(value) != 7 or not value.startswith("#"):
        return None
    try:
        return int(value[1:3], 16) / 255, int(value[3:5], 16) / 255, int(value[5:7], 16) / 255
    except ValueError:
        return None


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else float(((c + 0.055) / 1.055) ** 2.4)


def luminance(hex_color: str) -> float | None:
    rgb = _hex(hex_color)
    if rgb is None:
        return None
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float | None:
    la, lb = luminance(a), luminance(b)
    if la is None or lb is None:
        return None
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def resolve(color: str | None, tokens: Mapping[str, Any], default: str) -> str | None:
    """``#rrggbb``, ``token:name`` (theme), empty (``default``) or ``transparent`` (None: see through)."""
    if not color:
        color = default
    if color == "transparent":
        return None
    if color.startswith("token:"):
        mode = str(tokens.get("mode") or "dark")
        value = tokens.get(f"{mode}_{color[6:]}") or tokens.get(color[6:])
        return str(value) if value else None
    return color


def min_font_size(viewing_distance_m: float, screen_height_m: float) -> float:
    """Smallest font size (% of the canvas height) readable from ``viewing_distance_m``."""
    letter = viewing_distance_m * LETTER_PER_M
    return round(letter / CAP / max(screen_height_m, 0.05) * 100, 1)


def _contains(text: Any, names: Sequence[str]) -> bool:
    s = str(text or "").replace(" ", "")
    return any("{{" + n in s for n in names)


def _overlaps(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    fa, fb = a.get("frame") or {}, b.get("frame") or {}
    try:
        return not (fa["x"] + fa["w"] <= fb["x"] or fb["x"] + fb["w"] <= fa["x"]
                    or fa["y"] + fa["h"] <= fb["y"] or fb["y"] + fb["h"] <= fa["y"])
    except (KeyError, TypeError):
        return False


def lint(data: Mapping[str, Any], *, zones_model: bool, tokens: Mapping[str, Any] | None = None,
         viewing_distance_m: float = 8.0, screen_height_m: float = 0.6) -> list[Finding]:
    tokens = tokens or {}
    out: list[Finding] = []
    elements = [e for e in data.get("elements") or [] if isinstance(e, Mapping) and not e.get("hidden")]
    texts = [e for e in elements if e.get("type") in TEXT_TYPES]
    signs = [e for e in elements if e.get("type") == "pictogram"]
    if not signs:
        out.append(Finding("error", "pictogram", "Add a safety sign (ISO 7010 pictogram)."))
    if not texts:
        out.append(Finding("error", "text", "Add a text that tells people what to do."))
    if zones_model:
        has_dir = any(str((e.get("props") or {}).get("code")) == "arrow" for e in signs) or any(
            _contains((e.get("props") or {}).get("text"), DIRECTION_VARS) for e in texts)
        if not has_dir:
            out.append(Finding("error", "direction", "Add a direction arrow (safety sign “arrow”) or the "
                                                     "{{ evac.direction }} text for the zones-and-routes model."))
    bg = data.get("background") or {}
    page = resolve(str(bg.get("color") or ""), tokens, "token:background") if not bg.get("asset") else None
    smallest = min_font_size(viewing_distance_m, screen_height_m)
    for e in texts:
        style = e.get("style") or {}
        eid = str(e.get("id"))
        # what is behind the text: its own background, else the topmost shape below it, else the page
        behind = resolve(str(style.get("background") or ""), tokens, "transparent")
        if behind is None:
            for other in reversed(elements[:elements.index(e)]):
                if other.get("type") == "shape" and _overlaps(other, e):
                    behind = resolve(str((other.get("style") or {}).get("background") or ""), tokens, "transparent")
                    if behind is not None:
                        break
        behind = behind or page
        fg = resolve(str(style.get("color") or ""), tokens, "token:text")
        ratio = contrast(fg, behind) if fg and behind else None
        if ratio is None:
            out.append(Finding("warning", "contrast_unknown", "Check the contrast yourself: the text is on an image "
                                                               "or uses a colour EVAC cannot read.", eid))
        elif ratio < 4.5:
            out.append(Finding("error", "contrast", f"Contrast {ratio:.1f}:1 is too low (at least 4.5:1, better 7:1).",
                               eid))
        elif ratio < 7:
            out.append(Finding("warning", "contrast", f"Contrast {ratio:.1f}:1: 7:1 or more reads better in smoke "
                                                      "and from far away.", eid))
        size = style.get("fontSize")
        if isinstance(size, (int, float)) and not (e.get("props") or {}).get("autofit"):
            if size < smallest / 2:
                out.append(Finding("error", "size", f"Text too small: {size} % of the screen height, at least "
                                                    f"{smallest} % for {viewing_distance_m:g} m.", eid))
            elif size < smallest:
                out.append(Finding("warning", "size", f"Text small for {viewing_distance_m:g} m: {size} %, "
                                                      f"recommended {smallest} %.", eid))
    return out
