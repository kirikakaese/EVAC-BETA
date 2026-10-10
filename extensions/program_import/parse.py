# SPDX-License-Identifier: AGPL-3.0-or-later
"""Program formats → ``apps.schedule.services.Imported`` (ADR-0038).

- frab / Pentabarf ``schedule.xml`` (also what pretalx exports): days > rooms > events with ``date`` (ISO with
  offset) or ``start`` (HH:MM on the day), ``duration`` (HH:MM), ``guid``/``id``, persons.
- frab JSON ``schedule.json`` (pretalx's JSON export): the same tree as JSON.
- iCalendar: VEVENTs with ``UID``, ``DTSTART``/``DTEND`` or ``DURATION`` (UTC, ``TZID=`` or floating in the event's
  time zone), ``SUMMARY``, ``LOCATION`` (the stage), ``DESCRIPTION``, ``CATEGORIES`` (the track), ``STATUS``.

Everything here is pure (bytes in, list out) so it can be tested without a network.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import zoneinfo
from typing import Any
from xml.etree import ElementTree as ET

from apps.schedule.services import Imported


class ParseError(ValueError):
    pass


def _zone(name: str) -> dt.tzinfo:
    try:
        return zoneinfo.ZoneInfo(name or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return dt.UTC


def _duration(value: str) -> dt.timedelta:
    """frab durations: ``HH:MM`` or ``HH:MM:SS`` (also ``D:HH:MM``)."""
    parts = [int(p) for p in (value or "0:0").strip().split(":") if p.strip().isdigit()]
    if len(parts) == 2:
        return dt.timedelta(hours=parts[0], minutes=parts[1])
    if len(parts) == 3:
        return dt.timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
    if len(parts) == 4:
        return dt.timedelta(days=parts[0], hours=parts[1], minutes=parts[2], seconds=parts[3])
    raise ParseError(f"bad duration {value!r}")


def _aware(value: dt.datetime, tz: dt.tzinfo) -> dt.datetime:
    return value if value.tzinfo else value.replace(tzinfo=tz)


def _start(date_text: str, day: str, start: str, tz: dt.tzinfo) -> dt.datetime:
    if date_text:
        try:
            return _aware(dt.datetime.fromisoformat(date_text.strip().replace("Z", "+00:00")), tz)
        except ValueError:
            pass
    if day and start:
        return _aware(dt.datetime.fromisoformat(f"{day.strip()}T{start.strip()}"), tz)
    raise ParseError("an event without a date")


def _text(node: Any, tag: str) -> str:
    child = node.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def frab_xml(data: bytes, timezone_name: str = "UTC") -> list[Imported]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError(f"not XML: {exc}") from None
    if root.tag != "schedule":
        raise ParseError("not a frab schedule (no <schedule>)")
    conf_tz = _text(root.find("conference") if root.find("conference") is not None else root, "time_zone_name")
    tz = _zone(conf_tz or timezone_name)
    out = []
    for day in root.iter("day"):
        for room in day.iter("room"):
            for e in room.iter("event"):
                ext = e.get("guid") or e.get("id") or ""
                try:
                    start = _start(_text(e, "date"), day.get("date", ""), _text(e, "start"), tz)
                    end = start + _duration(_text(e, "duration") or "0:0")
                except (ParseError, ValueError) as exc:
                    raise ParseError(f"event {ext}: {exc}") from None
                people = [(p.get("guid") or p.get("id") or "", (p.text or "").strip())
                          for p in (e.find("persons") if e.find("persons") is not None else [])]
                title = _text(e, "title")
                out.append(Imported(
                    external_id=ext, title=title, starts_at=start, ends_at=end,
                    stage=_text(e, "room") or room.get("name", ""), track=_text(e, "track"),
                    subtitle=_text(e, "subtitle"), abstract=_text(e, "abstract") or _text(e, "description"),
                    language=_text(e, "language"), kind=_text(e, "type"), url=_text(e, "url"), speakers=people,
                    cancelled=title.upper().startswith(("CANCELLED:", "CANCELED:", "ABGESAGT:"))))
    return out


def frab_json(data: bytes, timezone_name: str = "UTC") -> list[Imported]:
    try:
        doc = json.loads(data)
    except ValueError as exc:
        raise ParseError(f"not JSON: {exc}") from None
    sched = doc.get("schedule") if isinstance(doc, dict) else None
    conf = (sched or {}).get("conference") if isinstance(sched, dict) else None
    if not isinstance(conf, dict) or not isinstance(conf.get("days"), list):
        raise ParseError("not a frab/pretalx schedule.json (no schedule.conference.days)")
    tz = _zone(conf.get("time_zone_name") or timezone_name)
    out = []
    for day in conf["days"]:
        rooms = day.get("rooms") or {}
        for room_name, events in (rooms.items() if isinstance(rooms, dict) else []):
            for e in events or []:
                if not isinstance(e, dict):
                    continue
                ext = str(e.get("guid") or e.get("id") or "")
                try:
                    start = _start(str(e.get("date") or ""), str(day.get("date") or ""), str(e.get("start") or ""),
                                   tz)
                    end = start + _duration(str(e.get("duration") or "0:0"))
                except (ParseError, ValueError) as exc:
                    raise ParseError(f"event {ext}: {exc}") from None
                people = [(str(p.get("guid") or p.get("code") or p.get("id") or ""),
                           str(p.get("public_name") or p.get("name") or "")) for p in e.get("persons") or []
                          if isinstance(p, dict)]
                title = str(e.get("title") or "")
                out.append(Imported(
                    external_id=ext, title=title, starts_at=start, ends_at=end,
                    stage=str(e.get("room") or room_name or ""), track=str(e.get("track") or ""),
                    subtitle=str(e.get("subtitle") or ""), abstract=str(e.get("abstract") or e.get("description")
                                                                         or ""),
                    language=str(e.get("language") or ""), kind=str(e.get("type") or ""),
                    url=str(e.get("url") or ""), speakers=people,
                    cancelled=title.upper().startswith(("CANCELLED:", "CANCELED:"))))
    return out


# ------------------------------------------------------------------ iCalendar
_DUR = re.compile(r"^(?P<sign>[+-])?P(?:(?P<w>\d+)W)?(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?"
                  r"(?:(?P<s>\d+)S)?)?$")


def _ical_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        elif raw.strip():
            out.append(raw)
    return out


def _ical_split(line: str) -> tuple[str, dict[str, str], str]:
    head, _sep, value = line.partition(":")
    name, *params = head.split(";")
    return name.upper(), {k.upper(): v.strip('"') for k, _s, v in (p.partition("=") for p in params)}, value


def _ical_unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace(
        "\\\\", "\\")


def _ical_time(value: str, params: dict[str, str], tz: dt.tzinfo) -> tuple[dt.datetime, bool]:
    """(time, all_day)."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        d = dt.datetime.strptime(value[:8], "%Y%m%d")
        return d.replace(tzinfo=tz), True
    fmt = "%Y%m%dT%H%M%S" if len(value.rstrip("Z")) == 15 else "%Y%m%dT%H%M"
    t = dt.datetime.strptime(value.rstrip("Z"), fmt)
    if value.endswith("Z"):
        return t.replace(tzinfo=dt.UTC), False
    return t.replace(tzinfo=_zone(params["TZID"]) if params.get("TZID") else tz), False


def _ical_duration(value: str) -> dt.timedelta:
    m = _DUR.match(value.strip())
    if not m:
        raise ParseError(f"bad DURATION {value!r}")
    d = dt.timedelta(weeks=int(m["w"] or 0), days=int(m["d"] or 0), hours=int(m["h"] or 0),
                     minutes=int(m["m"] or 0), seconds=int(m["s"] or 0))
    return -d if m["sign"] == "-" else d


def ical(data: bytes, timezone_name: str = "UTC") -> list[Imported]:
    text = data.decode("utf-8", errors="replace")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise ParseError("not an iCalendar file (no BEGIN:VCALENDAR)")
    tz = _zone(timezone_name)
    out: list[Imported] = []
    cur: dict[str, Any] | None = None
    for line in _ical_lines(text):
        name, params, value = _ical_split(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            cur = {}
        elif name == "END" and value.upper() == "VEVENT" and cur is not None:
            if cur.get("start") and not cur.get("all_day") and cur.get("uid"):
                start = cur["start"]
                end = cur.get("end") or start + cur.get("duration", dt.timedelta(hours=1))
                if cur.get("recurring"):
                    cur = None
                    continue
                uid = cur["uid"] + (f"#{cur['recurrence']}" if cur.get("recurrence") else "")
                out.append(Imported(external_id=uid, title=cur.get("summary", ""), starts_at=start,
                                    ends_at=end, stage=cur.get("location", ""), track=cur.get("category", ""),
                                    abstract=cur.get("description", ""), url=cur.get("url", ""),
                                    cancelled=cur.get("status") == "CANCELLED"))
            cur = None
        elif cur is not None:
            try:
                if name == "UID":
                    cur["uid"] = value.strip()
                elif name == "RECURRENCE-ID":
                    cur["recurrence"] = value.strip()
                elif name == "RRULE":
                    cur["recurring"] = True
                elif name == "DTSTART":
                    cur["start"], cur["all_day"] = _ical_time(value, params, tz)
                elif name == "DTEND":
                    cur["end"] = _ical_time(value, params, tz)[0]
                elif name == "DURATION":
                    cur["duration"] = _ical_duration(value)
                elif name == "SUMMARY":
                    cur["summary"] = _ical_unescape(value)
                elif name == "LOCATION":
                    cur["location"] = _ical_unescape(value)
                elif name == "DESCRIPTION":
                    cur["description"] = _ical_unescape(value)
                elif name == "CATEGORIES":
                    cur["category"] = _ical_unescape(value).split(",")[0].strip()
                elif name == "URL":
                    cur["url"] = value.strip()
                elif name == "STATUS":
                    cur["status"] = value.strip().upper()
            except ValueError as exc:
                raise ParseError(f"{name}: {exc}") from None
    return out
