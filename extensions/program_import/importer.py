# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetch a program source and merge it into the event's program (roadmap 5.2, ADR-0038).

Three extensions share this code: ``pretalx`` (instance URL + event slug, optional API token; reads pretalx's
frab-compatible ``schedule.json``), ``frab`` (any ``schedule.xml`` URL, also Pentabarf and pretalx) and ``ical`` (an
``.ics`` URL). A sync runs in the outbox (``Sync now``, the periodic beat task); the merge keeps local changes
(``Session.overrides``) and reports what happened in the extension log.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import outbox, safefetch
from apps.core.plugins import ConnectionResult

from . import parse

JOB = "program_import.sync"
KEYS = ("pretalx", "frab", "ical")


def source_of(config: Any) -> str:
    return f"{config.extension}:{config.pk}"


def url_of(config: Any) -> str:
    s = config.settings or {}
    if config.extension == "pretalx":
        base = str(s.get("base_url") or "").rstrip("/")
        return f"{base}/{str(s.get('event') or '').strip('/')}/schedule/export/schedule.json" if base else ""
    return str(s.get("url") or "")


def fetch(config: Any) -> list[Any]:
    """Download and parse; raises ``safefetch.FetchError`` or ``parse.ParseError``."""
    url = url_of(config)
    if not url:
        raise safefetch.FetchError(_("No URL configured."))
    headers = {}
    token = config.secret("token") if config.extension == "pretalx" else ""
    if token:
        headers["Authorization"] = f"Token {token}"
    got = safefetch.get(url, headers=headers, allow_private=bool(getattr(settings, "EVAC_IMPORT_ALLOW_PRIVATE",
                                                                         False)),
                        max_bytes=20 * 1024 * 1024)
    tzname = config.event.timezone if config.event_id else "UTC"
    if config.extension == "ical":
        return parse.ical(got.body, tzname)
    body = got.body.lstrip()
    return parse.frab_json(got.body, tzname) if body[:1] in (b"{", b"[") else parse.frab_xml(got.body, tzname)


def run(config: Any, *, actor: Any = None) -> Any:
    """Fetch, merge, record. Returns the ImportResult (or raises)."""
    from apps.extensions import services as ext
    from apps.schedule import services as program

    items = fetch(config)
    result = program.merge(config.event, source_of(config), items, actor=actor)
    config.last_sync_at = timezone.now()
    config.last_error = ""
    config.save(update_fields=["last_sync_at", "last_error"])
    ext.write_log(config, "info", f"Program sync: {result.summary()}",
                  errors=result.errors[:20])
    return result


def handle_job(job: Any) -> None:
    from apps.extensions import services as ext
    from apps.extensions.models import ExtensionConfig

    config = ExtensionConfig.objects.select_related("event").filter(pk=job.payload["config"], enabled=True).first()
    if config is None or config.event_id is None or not config.feature_enabled("sync"):
        job.result = {"skipped": "gone or disabled"}
        return
    from apps.core import modules

    if not modules.is_enabled("program", config.event):
        job.result = {"skipped": "program module off"}
        return
    try:
        result = run(config)
    except (safefetch.FetchError, parse.ParseError) as exc:
        config.last_error = str(exc)[:500]
        config.save(update_fields=["last_error"])
        ext.write_log(config, "error", f"Program sync failed: {exc}")
        job.result = {"failed": str(exc)[:300]}
        return
    job.result = {"summary": result.summary()}


def queue(config: Any, *, reason: str = "manual") -> Any:
    bucket = int(timezone.now().timestamp() // 30)
    return outbox.enqueue(JOB, {"config": str(config.pk), "reason": reason}, event=config.event,
                          key=f"program-sync:{config.pk}:{bucket}:{reason}")


def sync_due(now: dt.datetime | None = None) -> int:
    """Beat task: queue a sync for every enabled source whose interval has passed."""
    from apps.extensions.models import ExtensionConfig

    now = now or timezone.now()
    n = 0
    for config in ExtensionConfig.objects.filter(extension__in=KEYS, enabled=True, event__isnull=False):
        value = (config.settings or {}).get("interval_minutes")
        minutes = 15 if value is None or value == "" else int(value)
        if minutes <= 0 or not config.feature_enabled("sync"):
            continue
        if config.last_sync_at is None or config.last_sync_at + dt.timedelta(minutes=minutes) <= now:
            queue(config, reason="periodic")
            n += 1
    return n


def test_connection(config: Any) -> ConnectionResult:
    try:
        items = fetch(config)
    except (safefetch.FetchError, parse.ParseError) as exc:
        return ConnectionResult(False, str(exc))
    stages = sorted({i.stage for i in items if i.stage})
    first = min((i.starts_at for i in items), default=None)
    msg = _("%(n)s sessions on %(s)s stages found") % {"n": len(items), "s": len(stages)}
    if first:
        import zoneinfo

        try:
            tz = zoneinfo.ZoneInfo(config.event.timezone if config.event_id else "UTC")
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            tz = dt.UTC
        msg += _(", the first on %(d)s") % {"d": first.astimezone(tz).strftime("%a %d %b %H:%M")}
    return ConnectionResult(True, msg + ". " + _("Nothing was imported yet: use “Sync now”."))


def purge(config: Any) -> None:
    """Disconnect & purge: remove the sessions this source created (local sessions stay)."""
    from apps.schedule.models import Session

    Session.objects.filter(event=config.event, source=source_of(config)).delete()
