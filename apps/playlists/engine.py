# SPDX-License-Identifier: AGPL-3.0-or-later
"""Program resolution: which entry wins at a time and which slide of its playlist is on screen.

This is a line-by-line twin of ``frontend/src/program/engine.ts`` (the player runs that one). Both are tested
against the same vectors (``frontend/test/fixtures/program-vectors.json``), so the portal preview and calendar
show exactly what screens play. Pure functions over plain dicts; times are integer milliseconds since the epoch.

Program shape::

    {"entries": [{"id", "source", "name", "priority", "content": {"layout"|"playlist"|"message": id},
                  "windows": [[start_ms | None, end_ms | None], ...]}],
     "playlists": {id: {"mode": "ordered|shuffle|weighted", "default": ms,
                        "items": [{"id", "layout"|"playlist": id, "duration": ms|None, "weight": n,
                                   "tags": [...], "when": "expr", "from": ms|None, "until": ms|None}]}},
     "layouts": {id: duration_ms | None}}   # published layouts that can be shown
"""
from __future__ import annotations

import re
from typing import Any

Program = dict[str, Any]
Ctx = dict[str, Any]
Window = list[Any]  # [start_ms | None, end_ms | None]
Slide = dict[str, Any]

MAX_DEPTH = 5
FALLBACK_MS = 10_000
M32 = 0xFFFFFFFF


# ------------------------------------------------------------------ conditions (subset of renderer/template.ts)
def _lookup(variables: Ctx, path: str) -> Any:
    p = path.strip()
    if re.fullmatch(r'".*"|\'.*\'', p):
        return p[1:-1]
    if re.fullmatch(r"-?\d+(\.\d+)?", p):
        return float(p) if "." in p else int(p)
    cur: Any = variables
    for part in p.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ", ".join(_text(x) for x in v)
    if isinstance(v, dict):
        return str(v.get("name", ""))
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _filter(value: Any, f: str) -> Any:
    name, _, arg = f.partition(":")
    arg = arg.strip()
    if re.fullmatch(r'".*"|\'.*\'', arg):
        arg = arg[1:-1]
    name = name.strip()
    if name == "upper":
        return _text(value).upper()
    if name == "lower":
        return _text(value).lower()
    if name == "default":
        return arg if _text(value) == "" else value
    if name == "join":
        return (arg or ", ").join(_text(x) for x in value) if isinstance(value, list) else _text(value)
    return value


def _split(expr: str) -> list[str]:
    out, cur, quote = [], "", ""
    for ch in expr:
        if quote:
            if ch == quote:
                quote = ""
            cur += ch
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch == "|":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [x.strip() for x in out]


def evaluate(expr: str, variables: Ctx) -> Any:
    head, *filters = _split(expr)
    value = _lookup(variables, head)
    for f in filters:
        value = _filter(value, f)
    return value


def _truthy(v: Any) -> bool:
    if isinstance(v, list):
        return len(v) > 0
    return not (v is None or v is False or v == "" or v == 0)


def condition(expr: str, variables: Ctx) -> bool:
    e = (expr or "").strip()
    if not e:
        return True
    if e.startswith("not "):
        return not condition(e[4:], variables)
    m = re.match(r"^(.+?)\s*(==|!=)\s*(.+)$", e)
    if m:
        a, b = _text(evaluate(m.group(1), variables)), _text(evaluate(m.group(3), variables))
        return a == b if m.group(2) == "==" else a != b
    return _truthy(evaluate(re.sub(r"^\{\{|\}\}$", "", e), variables))


# ------------------------------------------------------------------ deterministic ordering
def fnv1a(s: str) -> int:
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & M32
    return h


def shuffled[T](items: list[T], seed: int) -> list[T]:
    x = seed or 1
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        x ^= (x << 13) & M32
        x ^= x >> 17
        x ^= (x << 5) & M32
        j = x % (i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def weighted[T](items: list[T], weights: list[int]) -> list[T]:
    """Smooth weighted round robin: weights 3:1 give a a b a, a a b a, … (no long runs)."""
    total = sum(weights)
    current = [0] * len(items)
    out: list[T] = []
    for _ in range(total):
        for i, w in enumerate(weights):
            current[i] += w
        best = max(range(len(items)), key=lambda i: (current[i], -i))
        current[best] -= total
        out.append(items[best])
    return out


# ------------------------------------------------------------------ playlists
def _item_active(item: dict[str, Any], t: int, ctx: Ctx) -> bool:
    if item.get("from") is not None and t < item["from"]:
        return False
    if item.get("until") is not None and t >= item["until"]:
        return False
    tags = item.get("tags") or []
    if tags and not set(tags) & set((ctx.get("screen") or {}).get("tags") or []):
        return False
    return condition(item.get("when") or "", ctx)


def flatten(program: Program, pid: str, ctx: Ctx, t: int, cycle: int, stack: tuple[str, ...] = ()) -> list[Slide]:
    """Slides of a playlist at time ``t``: ``[{"layout"|"message": id, "duration": ms, "item": id}]``."""
    pl = program.get("playlists", {}).get(pid)
    if pl is None or pid in stack or len(stack) >= MAX_DEPTH:
        return []
    layouts = program.get("layouts", {})
    units: list[list[Slide]] = []
    weights: list[int] = []
    for item in pl.get("items", []):
        if not _item_active(item, t, ctx):
            continue
        if item.get("playlist"):
            slides = flatten(program, item["playlist"], ctx, t, cycle, (*stack, pid))
        elif item.get("layout") in layouts:
            ms = item.get("duration") or layouts[item["layout"]] or pl.get("default") or FALLBACK_MS
            slides = [{"layout": item["layout"], "duration": ms, "item": item["id"]}]
        else:
            slides = []
        if slides:
            units.append(slides)
            weights.append(max(1, int(item.get("weight") or 1)))
    mode = pl.get("mode")
    if mode == "weighted":
        units = weighted(units, weights)
    elif mode == "shuffle":
        units = shuffled(units, fnv1a(f"{pid}:{cycle}"))
    return [s for unit in units for s in unit]


# ------------------------------------------------------------------ entries
def _contains(window: Window, t: int) -> bool:
    start, end = window
    return (start is None or start <= t) and (end is None or t < end)


def candidates(program: Program, t: int) -> list[tuple[dict[str, Any], Window]]:
    """Entries with a window containing ``t``, best first: priority, then later start, then list order."""
    found: list[tuple[tuple[int, int, int], dict[str, Any], Window]] = []
    for n, entry in enumerate(program.get("entries", [])):
        for w in entry.get("windows", []):
            if _contains(w, t):
                found.append(((-entry["priority"], -(w[0] if w[0] is not None else -1), n), entry, w))
                break
    found.sort(key=lambda f: f[0])
    return [(e, w) for _, e, w in found]


def _slide(program: Program, ctx: Ctx, t: int, entry: dict[str, Any], window: Window) -> Slide | None:
    content = entry["content"]
    base = {"entry": entry["id"], "index": 0, "count": 1, "start": window[0], "end": window[1]}
    if "message" in content:
        return {**base, "message": content["message"]} if content["message"] in program.get("messages", {}) else None
    if "layout" in content:
        return {**base, "layout": content["layout"]} if content["layout"] in program.get("layouts", {}) else None
    anchor = window[0] or 0
    slides = flatten(program, content["playlist"], ctx, t, 0)
    total = sum(s["duration"] for s in slides)
    if not total:
        return None
    cycle = (t - anchor) // total
    if cycle:  # the total length does not depend on the order; shuffled playlists reorder per cycle
        slides = flatten(program, content["playlist"], ctx, t, cycle)
    pos = (t - anchor) - cycle * total
    start = anchor + cycle * total
    for i, s in enumerate(slides):
        if pos < s["duration"]:
            end = start + s["duration"]
            if window[1] is not None:
                end = min(end, window[1])
            return {**base, "layout": s["layout"], "item": s["item"], "index": i, "count": len(slides),
                    "start": start, "end": end}
        pos -= s["duration"]
        start += s["duration"]
    return None  # pragma: no cover - pos < total always hits a slide


def slide_at(program: Program, ctx: Ctx, t: int) -> Slide | None:
    """``{"entry", "layout"|"message", "item"?, "index", "count", "start", "end"}`` at ``t``, or None.

    An entry with nothing to show on this screen (unpublished layout, every item filtered out) gives way to
    the next one."""
    for entry, window in candidates(program, t):
        slide = _slide(program, ctx, t, entry, window)
        if slide is not None:
            return slide
    return None


def next_change(program: Program, t: int, slide: Slide | None) -> int | None:
    """The earliest time after ``t`` when the result can change (slide end or any window boundary)."""
    times = [slide["end"]] if slide and slide.get("end") is not None else []
    for entry in program.get("entries", []):
        for start, end in entry.get("windows", []):
            times += [x for x in (start, end) if x is not None and x > t]
    return min(times) if times else None
