# SPDX-License-Identifier: AGPL-3.0-or-later
"""Program exports for the public (brief §11.1): iCalendar, JSON and frab-compatible schedule XML.

Only public sessions; cancelled ones stay in the export with their status (iCal ``STATUS:CANCELLED``, frab
``<title>`` prefixed), so calendars that already hold them update instead of keeping a stale entry.
"""
from __future__ import annotations

import datetime as dt
import zoneinfo
from typing import Any
from xml.etree import ElementTree as ET

from django.utils import timezone

from .models import Session


def sessions(event: Any) -> Any:
    return (Session.objects.filter(event=event, public=True).select_related("stage", "track")
            .prefetch_related("speakers").order_by("starts_at", "stage__order"))


def _tz(event: Any) -> dt.tzinfo:
    try:
        return zoneinfo.ZoneInfo(event.timezone or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return dt.UTC


# ------------------------------------------------------------------ iCalendar
def _ics_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace(
        "\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines longer than 75 octets continue on the next line after a space."""
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode())
            cur = b""
        cur += b
    parts.append(cur.decode())
    return "\r\n ".join(parts)


def _utc(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def ical(event: Any, host: str) -> str:
    now = _utc(timezone.now())
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EVAC//Program//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_ics_escape(event.name)}", f"X-WR-TIMEZONE:{event.timezone or 'UTC'}"]
    for s in sessions(event):
        desc = s.abstract
        if s.speakers.all():
            desc = ", ".join(p.name for p in s.speakers.all()) + ("\n\n" + desc if desc else "")
        if s.note:
            desc = f"{s.note}\n\n{desc}" if desc else s.note
        lines += ["BEGIN:VEVENT", f"UID:{s.pk}@{host}", f"DTSTAMP:{now}", f"DTSTART:{_utc(s.starts_at)}",
                  f"DTEND:{_utc(s.ends_at)}", f"SUMMARY:{_ics_escape(s.title)}", f"SEQUENCE:{s.version}",
                  f"LAST-MODIFIED:{_utc(s.updated_at)}"]
        if s.stage_id:
            lines.append(f"LOCATION:{_ics_escape(s.stage.name)}")
        if desc:
            lines.append(f"DESCRIPTION:{_ics_escape(desc)}")
        if s.track_id:
            lines.append(f"CATEGORIES:{_ics_escape(s.track.name)}")
        if s.url:
            lines.append(f"URL:{s.url}")
        lines.append("STATUS:CANCELLED" if s.status == Session.Status.CANCELLED else "STATUS:CONFIRMED")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


# ------------------------------------------------------------------ JSON
def as_json(event: Any) -> dict[str, Any]:
    from .services import session_data

    return {"event": {"slug": event.slug, "name": event.name, "timezone": event.timezone},
            "stages": [{"id": str(st.pk), "name": st.name} for st in event.stages.all()],
            "sessions": [{**session_data(s), "abstract": s.abstract, "url": s.url} for s in sessions(event)]}


# ------------------------------------------------------------------ frab XML
def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def frab(event: Any) -> bytes:
    """``schedule.xml`` as frab/pretalx write it: days (06:00 to 06:00 local time) > rooms > events."""
    tz = _tz(event)
    root = ET.Element("schedule")
    ET.SubElement(root, "version").text = timezone.now().strftime("%Y-%m-%d %H:%M")
    conf = ET.SubElement(root, "conference")
    ET.SubElement(conf, "acronym").text = event.slug
    ET.SubElement(conf, "title").text = event.name
    if event.start_date:
        ET.SubElement(conf, "start").text = event.start_date.isoformat()
    if event.end_date:
        ET.SubElement(conf, "end").text = event.end_date.isoformat()
    ET.SubElement(conf, "time_zone_name").text = event.timezone or "UTC"
    days: dict[dt.date, dict[str, list[Session]]] = {}
    for s in sessions(event):
        local = s.starts_at.astimezone(tz)
        day = (local - dt.timedelta(hours=6)).date()
        days.setdefault(day, {}).setdefault(s.stage.name if s.stage_id else "", []).append(s)
    for index, (day, rooms) in enumerate(sorted(days.items()), start=1):
        start = dt.datetime.combine(day, dt.time(6), tz)
        d = ET.SubElement(root, "day", index=str(index), date=day.isoformat(), start=start.isoformat(),
                          end=(start + dt.timedelta(days=1)).isoformat())
        for room_name, items in rooms.items():
            room = ET.SubElement(d, "room", name=room_name)
            for s in items:
                local = s.starts_at.astimezone(tz)
                e = ET.SubElement(room, "event", guid=str(s.pk), id=str(s.pk.int % 10 ** 9))
                ET.SubElement(e, "date").text = local.isoformat()
                ET.SubElement(e, "start").text = local.strftime("%H:%M")
                ET.SubElement(e, "duration").text = _hhmm(int((s.ends_at - s.starts_at).total_seconds() // 60))
                ET.SubElement(e, "room").text = room_name
                ET.SubElement(e, "slug").text = f"{event.slug}-{str(s.pk)[:8]}"
                title = s.title if s.status != Session.Status.CANCELLED else f"CANCELLED: {s.title}"
                ET.SubElement(e, "title").text = title
                ET.SubElement(e, "subtitle").text = s.subtitle
                ET.SubElement(e, "track").text = s.track.name if s.track_id else ""
                ET.SubElement(e, "type").text = s.kind
                ET.SubElement(e, "language").text = s.language
                ET.SubElement(e, "abstract").text = s.abstract
                ET.SubElement(e, "description").text = s.note
                persons = ET.SubElement(e, "persons")
                for p in s.speakers.all():
                    ET.SubElement(persons, "person", id=str(p.pk.int % 10 ** 9)).text = p.name
                if s.url:
                    ET.SubElement(e, "url").text = s.url
    ET.indent(root)
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="utf-8")
