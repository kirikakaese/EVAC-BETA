# SPDX-License-Identifier: AGPL-3.0-or-later
"""JSONPath subset and field mapping (ADR-0023).

Supported: ``$`` (the root), ``.key`` / ``key``, ``["key"]`` / ``['key']``, ``[n]`` (negative from the end) and
``[*]`` (every element). That covers "where is the list" and "which field of an item"; filters and recursive
descent are deliberately left out (they are where JSONPath dialects disagree).
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

TOKEN = re.compile(r"""\.?([A-Za-z_@$][\w@$-]*)|\[\s*(-?\d+)\s*\]|\[\s*\*\s*\]|\[\s*(['"])(.*?)\3\s*\]""")
FIELDS = ("title", "subtitle", "value", "label", "time", "end", "image", "link")
MAX_ROWS = 50


class PathError(ValueError):
    pass


def tokens(path: str) -> list[Any]:
    path = (path or "").strip()
    if path.startswith("$"):
        path = path[1:]
    out: list[Any] = []
    pos = 0
    while pos < len(path):
        m = TOKEN.match(path, pos)
        if not m or m.end() == pos:
            raise PathError(f"Cannot read the path at “{path[pos:pos + 12]}”.")
        if m.group(1) is not None:
            out.append(m.group(1))
        elif m.group(2) is not None:
            out.append(int(m.group(2)))
        elif m.group(4) is not None:
            out.append(m.group(4))
        else:
            out.append("*")
        pos = m.end()
    return out


def select(data: Any, path: str) -> list[Any]:
    """Every value the path points to (a list, also for a single match)."""
    current = [data]
    for tok in tokens(path):
        nxt: list[Any] = []
        for value in current:
            if tok == "*":
                if isinstance(value, list):
                    nxt.extend(value)
                elif isinstance(value, dict):
                    nxt.extend(value.values())
            elif isinstance(tok, int):
                if isinstance(value, list) and -len(value) <= tok < len(value):
                    nxt.append(value[tok])
            elif isinstance(value, dict) and tok in value:
                nxt.append(value[tok])
        current = nxt
    return current


def first(data: Any, path: str) -> Any:
    found = select(data, path)
    return found[0] if found else None


def items(data: Any, path: str) -> list[Any]:
    """The items of a widget: the path's match if that is a list, else all matches."""
    found = select(data, path or "$")
    if len(found) == 1 and isinstance(found[0], list):
        return found[0]
    return found


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (list, dict)):
        return ", ".join(str(_scalar(v)) for v in (value if isinstance(value, list) else value.values()))[:500]
    return str(value)[:1000]


def _when(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)


def rows(data: Any, items_path: str, fields: dict[str, str], *, limit: int = 20, upcoming: bool = False,
         now: dt.datetime | None = None) -> list[dict[str, Any]]:
    """Map the items to rows of the known fields (``title``, ``value``, ``time`` …); unmapped fields are left out.
    ``upcoming`` drops items whose end (or time) lies in the past."""
    now = now or dt.datetime.now(dt.UTC)
    out = []
    for item in items(data, items_path):
        row = {}
        for name in FIELDS:
            path = (fields or {}).get(name, "").strip()
            if path:
                row[name] = _scalar(first(item, path))
        if upcoming:
            when = _when(row.get("end")) or _when(row.get("time"))
            if when is not None and when < now:
                continue
        out.append(row)
        if len(out) >= min(limit, MAX_ROWS):
            break
    return out


def tree(data: Any, path: str = "$", depth: int = 0, *, max_children: int = 30, max_depth: int = 6) -> dict:
    """A JSON-like value as an explorable tree for the builder: each node knows its path."""
    node: dict[str, Any] = {"path": path}
    if isinstance(data, dict):
        node["kind"] = "object"
        node["size"] = len(data)
        if depth < max_depth:
            node["children"] = [
                {"key": k, **tree(v, f"{path}.{k}" if re.fullmatch(r"[A-Za-z_]\w*", k) else f'{path}["{k}"]',
                                  depth + 1, max_children=max_children, max_depth=max_depth)}
                for k, v in list(data.items())[:max_children]]
    elif isinstance(data, list):
        node["kind"] = "list"
        node["size"] = len(data)
        if depth < max_depth:
            node["children"] = [{"key": f"[{i}]", **tree(v, f"{path}[{i}]", depth + 1, max_children=max_children,
                                                           max_depth=max_depth)}
                                for i, v in enumerate(data[:min(3, max_children)])]
    else:
        node["kind"] = "value"
        node["value"] = _scalar(data)
    return node
