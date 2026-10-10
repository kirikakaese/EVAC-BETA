# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sanitising uploaded SVG files (pictures for screens, floor plans): everything that can run code or load
external resources is removed."""
from __future__ import annotations

import re

from defusedxml import ElementTree as SafeET

SVG_NS = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}href"
FORBIDDEN_TAGS = {"script", "foreignObject", "iframe", "embed", "object", "audio", "video", "handler", "listener"}
URL_IN_STYLE = re.compile(r"url\(\s*['\"]?\s*(?!#)", re.I)


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def sanitize_svg(data: bytes) -> bytes:
    """Remove everything that can run code or load external resources from an SVG."""
    root = SafeET.fromstring(data)
    for parent in list(root.iter()):
        for child in list(parent):
            if not isinstance(child.tag, str) or _local(child.tag) in FORBIDDEN_TAGS:
                parent.remove(child)
    for el in root.iter():
        for attr in list(el.attrib):
            name = _local(attr).lower()
            value = el.attrib[attr].strip()
            if name.startswith("on"):
                del el.attrib[attr]
            elif name == "href" or attr == XLINK:
                if not (value.startswith("#") or value.startswith("data:image/")):
                    del el.attrib[attr]
            elif name == "style" and (URL_IN_STYLE.search(value) or "expression(" in value.lower()):
                del el.attrib[attr]
        if _local(el.tag) == "style" and el.text and (URL_IN_STYLE.search(el.text) or "@import" in el.text):
            el.text = ""
    from xml.etree import ElementTree as ET  # noqa: S405 - serialising an already parsed, sanitised tree

    ET.register_namespace("", SVG_NS.strip("{}"))
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def size(data: bytes) -> tuple[float, float] | None:
    """Width and height of an SVG in user units (from width/height or the viewBox), or None."""
    root = SafeET.fromstring(data)
    box = (root.get("viewBox") or "").replace(",", " ").split()
    try:
        if len(box) == 4:
            return float(box[2]), float(box[3])
        w, h = (float(re.sub(r"[a-z%]+$", "", root.get(k, "") or "x")) for k in ("width", "height"))
        return w, h
    except ValueError:
        return None
