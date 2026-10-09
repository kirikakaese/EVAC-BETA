# SPDX-License-Identifier: AGPL-3.0-or-later
"""Font uploads: read WOFF2/WOFF/TTF/OTF with fontTools, detect family, weight, style and variable axes,
optionally subset to Latin (+ arrows and symbols used on signage), and store as WOFF2."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fontTools import subset as ft_subset
from fontTools.ttLib import TTFont, TTLibError

FORMATS = {"woff2", "woff", "ttf", "otf"}
#: Latin, Latin-1, Latin Extended-A, punctuation, currency, arrows, a few symbols (signage needs arrows)
LATIN_RANGE = ("U+0000-024F,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0300-036F,U+2000-206F,U+20A0-20CF,U+2100-214F,"
               "U+2190-21FF,U+2212,U+2215,U+25A0-25FF,U+FEFF,U+FFFD")


class FontError(ValueError):
    pass


@dataclass
class FontInfo:
    family: str
    weight_min: int
    weight_max: int
    style: str
    axes: list[dict[str, Any]] = field(default_factory=list)
    original_format: str = ""
    woff2: bytes = b""
    unicode_range: str = ""


def _codepoints(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.strip().removeprefix("U+").partition("-")
        start = int(a, 16)
        out.extend(range(start, int(b, 16) + 1 if b else start + 1))
    return out


def read(src: Path, original_name: str, *, subset: bool = False) -> FontInfo:
    fmt = Path(original_name).suffix.lower().lstrip(".")
    if fmt not in FORMATS:
        raise FontError("Upload a WOFF2, WOFF, TTF or OTF font.")
    try:
        font = TTFont(src, lazy=False)
    except (TTLibError, OSError, AssertionError, KeyError, ValueError) as exc:
        raise FontError("This file is not a readable font.") from exc
    if "name" not in font or "OS/2" not in font:
        raise FontError("This font has no name or OS/2 table.")
    family = (font["name"].getBestFamilyName() or Path(original_name).stem)[:120]
    os2 = font["OS/2"]
    weight = int(getattr(os2, "usWeightClass", 400) or 400)
    italic = bool(os2.fsSelection & 1) or bool(font["head"].macStyle & 2)
    axes = []
    if "fvar" in font:
        for ax in font["fvar"].axes:
            name = font["name"].getDebugName(ax.axisNameID) or ax.axisTag
            axes.append({"tag": ax.axisTag, "min": ax.minValue, "max": ax.maxValue, "default": ax.defaultValue,
                         "name": name})
    wght = next((a for a in axes if a["tag"] == "wght"), None)
    unicode_range = ""
    if subset:
        options = ft_subset.Options()
        options.layout_features = ["*"]
        options.name_IDs = ["*"]
        options.notdef_outline = True
        sub = ft_subset.Subsetter(options)
        sub.populate(unicodes=_codepoints(LATIN_RANGE))
        sub.subset(font)
        unicode_range = LATIN_RANGE
    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    return FontInfo(
        family=family, weight_min=int(wght["min"]) if wght else weight,
        weight_max=int(wght["max"]) if wght else weight,
        style="italic" if italic else "normal", axes=axes, original_format=fmt, woff2=buf.getvalue(),
        unicode_range=unicode_range)


def face_css(css_family: str, url: str, *, weight_min: int, weight_max: int, style: str,
             unicode_range: str = "") -> str:
    weight = str(weight_min) if weight_min == weight_max else f"{weight_min} {weight_max}"
    rng = f"unicode-range:{unicode_range};" if unicode_range else ""
    return (f'@font-face{{font-family:"{css_family}";src:url("{url}") format("woff2");font-weight:{weight};'
            f"font-style:{style};font-display:swap;{rng}}}")
