# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turn fetched bytes into plain JSON-like data (ADR-0023): JSON as is; RSS/Atom as ``{title, items: [...]}``;
iCal as ``{name, events: [...]}`` (single events; repeating events show their first date only); CSV as
``{rows: [...]}`` with the header row as keys. XML is parsed with defusedxml."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from typing import Any
from zoneinfo import ZoneInfo

from defusedxml import ElementTree as SafeET

MAX_ITEMS = 500


class ParseError(Exception):
    pass


def _text(data: bytes) -> str:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")  # pragma: no cover - latin-1 decodes everything


def parse(kind: str, data: bytes) -> Any:
    try:
        return {"json": parse_json, "rss": parse_feed, "ical": parse_ical, "csv": parse_csv}[kind](data)
    except ParseError:
        raise
    except Exception as exc:  # noqa: BLE001 - any parser error becomes a readable message
        raise ParseError(f"Not valid {kind.upper()}: {type(exc).__name__}") from None


def parse_json(data: bytes) -> Any:
    try:
        return json.loads(_text(data))
    except ValueError as exc:
        raise ParseError(f"Not valid JSON: {exc.msg} (line {exc.lineno})") from None


# ------------------------------------------------------------------ RSS / Atom
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el, *names: str) -> str:
    for c in el:
        if _local(c.tag) in names:
            if _local(c.tag) == "link" and c.get("href"):
                return c.get("href")
            return (c.text or "").strip()
    return ""


def parse_feed(data: bytes) -> dict[str, Any]:
    root = SafeET.fromstring(data)
    tag = _local(root.tag)
    if tag == "rss":
        channel = next((c for c in root if _local(c.tag) == "channel"), None)
        if channel is None:
            raise ParseError("RSS without a channel.")
        items = [c for c in channel if _local(c.tag) == "item"]
        title = _child(channel, "title")
    elif tag == "feed":  # Atom
        items = [c for c in root if _local(c.tag) == "entry"]
        title = _child(root, "title")
    elif tag == "RDF":  # RSS 1.0
        items = [c for c in root if _local(c.tag) == "item"]
        title = next((_child(c, "title") for c in root if _local(c.tag) == "channel"), "")
    else:
        raise ParseError("Neither RSS nor Atom.")
    return {"title": title, "items": [{
        "title": _child(i, "title"),
        "link": _child(i, "link"),
        "summary": re.sub(r"<[^>]+>", "", _child(i, "description", "summary", "content"))[:2000].strip(),
        "published": _child(i, "pubDate", "published", "updated", "date"),
        "author": _child(i, "author", "creator"),
    } for i in items[:MAX_ITEMS]]}


# ------------------------------------------------------------------ iCal
def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _ical_time(value: str, params: dict[str, str]) -> str:
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        return dt.date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", value)
    if not m:
        return value
    naive = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    if m.group(3):
        return naive.replace(tzinfo=dt.UTC).isoformat()
    tzid = params.get("TZID")
    if tzid:
        try:
            return naive.replace(tzinfo=ZoneInfo(tzid)).isoformat()
        except Exception:  # noqa: BLE001 - unknown zone: keep it floating
            pass
    return naive.isoformat()


def _ical_unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\",
                                                                                                         "\\")


def parse_ical(data: bytes) -> dict[str, Any]:
    lines = _unfold(_text(data))
    if not lines or lines[0].strip().upper() != "BEGIN:VCALENDAR":
        raise ParseError("Not an iCal calendar (BEGIN:VCALENDAR missing).")
    name, events, cur = "", [], None
    keys = {"SUMMARY": "summary", "DESCRIPTION": "description", "LOCATION": "location", "UID": "uid",
            "URL": "url", "DTSTART": "start", "DTEND": "end", "STATUS": "status", "CATEGORIES": "categories"}
    for line in lines:
        head, _sep, value = line.partition(":")
        prop, *raw_params = head.split(";")
        prop = prop.upper()
        params = dict(p.split("=", 1) for p in raw_params if "=" in p)
        if prop == "BEGIN" and value.upper() == "VEVENT":
            cur = {}
        elif prop == "END" and value.upper() == "VEVENT" and cur is not None:
            if cur.get("status", "").upper() != "CANCELLED":
                events.append(cur)
            cur = None
        elif cur is not None and prop in keys:
            cur[keys[prop]] = _ical_time(value, params) if prop in ("DTSTART", "DTEND") else _ical_unescape(value)
        elif cur is not None and prop == "RRULE":
            cur["repeats"] = value
        elif cur is None and prop == "X-WR-CALNAME":
            name = _ical_unescape(value)
    events.sort(key=lambda e: e.get("start", ""))
    return {"name": name, "events": events[:MAX_ITEMS]}


# ------------------------------------------------------------------ CSV
def parse_csv(data: bytes) -> dict[str, Any]:
    text = _text(data)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ParseError("The CSV has no header row.")
    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_ITEMS:
            break
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None})
    return {"columns": [f.strip() for f in reader.fieldnames], "rows": rows}
