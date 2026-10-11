# SPDX-License-Identifier: AGPL-3.0-or-later
"""pretix import and check-in sync (roadmap 8.2, ADR-0044).

Reads ``<url>/api/v1/organizers/<organizer>/events/<event>/`` with an API token (``Authorization: Token …``):
products with ``admission`` become ticket types, order positions of those products become attendees (the
position's ``secret`` is the ticket code, so the QR code on the pretix ticket works at EVAC's scanners). Paid
orders are valid, cancelled or expired ones cancelled; pending orders count as valid only when the setting says
so. Check-ins made with pretix's own scanners are taken over; EVAC's check-ins are sent back to a pretix check-in
list through the outbox (``pretix.checkin``), so both systems agree on who is inside.

Local data wins: ticket types and attendees edited in EVAC keep their zones, badges and notes; an attendee that
disappeared from pretix is cancelled, never deleted (its scans stay).
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from apps.core import outbox, safefetch
from apps.core.plugins import ConnectionResult

KEY = "pretix"
JOB = "pretix.sync"
CHECKIN_JOB = "pretix.checkin"
MAX_PAGES = 500


class SyncError(ValueError):
    pass


def source_of(config: Any) -> str:
    return f"{KEY}:{config.pk}"


def _allow_private() -> bool:
    return bool(getattr(settings, "EVAC_IMPORT_ALLOW_PRIVATE", False))


def _base(config: Any) -> str:
    s = config.settings or {}
    url, org, ev = (str(s.get(k) or "").strip().strip("/") for k in ("base_url", "organizer", "event"))
    if not url or not org or not ev:
        raise SyncError(_("Set the pretix URL, organizer and event."))
    return f"{url}/api/v1/organizers/{org}/events/{ev}"


def _headers(config: Any) -> dict[str, str]:
    token = config.secret("api_token")
    return {"Authorization": f"Token {token}", "Accept": "application/json"} if token else {"Accept":
                                                                                          "application/json"}


def _get(config: Any, url: str) -> Any:
    try:
        got = safefetch.get(url, headers=_headers(config), allow_private=_allow_private(),
                            max_bytes=50 * 1024 * 1024)
    except safefetch.FetchError as exc:
        raise SyncError(str(exc)) from None
    try:
        return json.loads(got.body)
    except ValueError:
        raise SyncError(_("pretix did not answer with JSON (is the URL right?).")) from None


def _all(config: Any, path: str) -> list[dict[str, Any]]:
    """Every page of a pretix list (``{"count", "next", "results"}``)."""
    url: str | None = f"{_base(config)}{path}"
    out: list[dict[str, Any]] = []
    for _page in range(MAX_PAGES):
        if not url:
            break
        doc = _get(config, url)
        if not isinstance(doc, dict) or not isinstance(doc.get("results"), list):
            raise SyncError(_("Unexpected answer from pretix."))
        out += [r for r in doc["results"] if isinstance(r, dict)]
        url = doc.get("next") or None
        if url and not url.startswith(_base(config).split("/api/v1/")[0]):
            raise SyncError(_("pretix pointed to another server."))
    return out


def text(value: Any) -> str:
    """pretix names are i18n dicts (``{"en": "Day ticket"}``)."""
    if isinstance(value, dict):
        return str(value.get("en") or next(iter(value.values()), "") or "")
    return str(value or "")


def fetch(config: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _all(config, "/items/"), _all(config, "/orders/?testmode=false")


def _when(value: Any) -> dt.datetime | None:
    d = parse_datetime(str(value or ""))
    return d if d is None or timezone.is_aware(d) else timezone.make_aware(d, dt.UTC)


def merge(config: Any, items: list[dict[str, Any]], orders: list[dict[str, Any]]) -> dict[str, int]:
    from apps.access.models import Attendee, TicketType

    event, source = config.event, source_of(config)
    pending_valid = bool((config.settings or {}).get("pending_valid"))
    stats = {"types": 0, "added": 0, "updated": 0, "cancelled": 0, "checked_in": 0, "skipped": 0}
    with transaction.atomic():
        types: dict[str, TicketType] = {}
        for it in items:
            if not it.get("admission", True) or it.get("id") is None:
                continue
            ext, name = str(it["id"]), text(it.get("name"))[:80] or f"pretix {it['id']}"
            t = (TicketType.objects.filter(event=event, source=source, external_id=ext).first()
                 or TicketType.objects.filter(event=event, name=name, source="").first())
            if t is None:
                t = TicketType.objects.create(event=event, name=name, source=source, external_id=ext)
                stats["types"] += 1
            else:
                t.source, t.external_id = source, ext
                if t.name != name and t.source == source:
                    t.name = name
                t.save(update_fields=["source", "external_id", "name"])
            types[ext] = t
        existing = {a.external_id: a for a in Attendee.objects.filter(event=event, source=source)}
        seen: set[str] = set()
        for order in orders:
            status = order.get("status")
            valid = status == "p" or (status == "n" and pending_valid)
            for p in order.get("positions") or []:
                t = types.get(str(p.get("item")))
                if t is None or not p.get("secret"):
                    stats["skipped"] += int(t is None and bool(p.get("secret")))
                    continue
                ext = f"{order.get('code')}-{p.get('positionid') or p.get('id')}"
                seen.add(ext)
                name = (p.get("attendee_name") or (p.get("attendee_name_parts") or {}).get("full_name")
                        or order.get("email") or ext)
                st = Attendee.Status.VALID if valid and not p.get("canceled") else Attendee.Status.CANCELLED
                a = existing.get(ext)
                values = {"name": str(name)[:150], "email": str(p.get("attendee_email") or order.get("email") or
                                                                 "")[:254],
                          "company": str(p.get("company") or "")[:150], "ticket_type": t,
                          "code": str(p["secret"])[:128], "status": st}
                if a is None:
                    a = Attendee.objects.filter(event=event, code=values["code"]).first()
                if a is None:
                    a = Attendee.objects.create(event=event, source=source, external_id=ext, **values)
                    stats["added"] += 1
                else:
                    dirty = [k for k, v in values.items() if getattr(a, k) != v]
                    if dirty or a.source != source or a.external_id != ext:
                        for k in dirty:
                            setattr(a, k, values[k])
                        a.source, a.external_id = source, ext
                        a.save()
                        stats["updated"] += 1
                times = [w for w in (_when(c.get("datetime")) for c in p.get("checkins") or []
                                     if c.get("type", "entry") == "entry") if w]
                if times and a.checked_in_at is None:
                    a.checked_in_at = min(times)
                    a.save(update_fields=["checked_in_at"])
                    stats["checked_in"] += 1
        for ext, a in existing.items():
            if ext not in seen and a.status == Attendee.Status.VALID:
                a.status = Attendee.Status.CANCELLED
                a.save(update_fields=["status"])
                stats["cancelled"] += 1
    return stats


def summary(stats: dict[str, int]) -> str:
    return _("%(a)s new and %(u)s changed attendees, %(c)s cancelled, %(i)s check-ins from pretix, %(t)s new ticket "
             "types") % {"a": stats["added"], "u": stats["updated"], "c": stats["cancelled"],
                         "i": stats["checked_in"], "t": stats["types"]}


def run(config: Any) -> dict[str, int]:
    from apps.extensions import services as ext

    items, orders = fetch(config)
    stats = merge(config, items, orders)
    config.last_sync_at = timezone.now()
    config.last_error = ""
    config.save(update_fields=["last_sync_at", "last_error"])
    ext.write_log(config, "info", f"pretix sync: {summary(stats)}")
    return stats


def _config(pk: Any) -> Any:
    from apps.extensions.models import ExtensionConfig

    return ExtensionConfig.objects.select_related("event").filter(pk=pk, enabled=True, extension=KEY).first()


def handle_job(job: Any) -> None:
    from apps.core import modules
    from apps.extensions import services as ext

    config = _config(job.payload["config"])
    if config is None or config.event_id is None or not config.feature_enabled("attendees"):
        job.result = {"skipped": "gone or disabled"}
        return
    if not modules.is_enabled("access", config.event):
        job.result = {"skipped": "access module off"}
        return
    try:
        stats = run(config)
    except SyncError as exc:
        config.last_error = str(exc)[:500]
        config.save(update_fields=["last_error"])
        ext.write_log(config, "error", f"pretix sync failed: {exc}")
        job.result = {"failed": str(exc)[:300]}
        return
    job.result = stats


def queue(config: Any, *, reason: str = "manual") -> Any:
    bucket = int(timezone.now().timestamp() // 30)
    return outbox.enqueue(JOB, {"config": str(config.pk), "reason": reason}, event=config.event,
                          key=f"pretix-sync:{config.pk}:{bucket}:{reason}")


def sync_due(now: dt.datetime | None = None) -> int:
    from apps.extensions.models import ExtensionConfig

    now = now or timezone.now()
    n = 0
    for config in ExtensionConfig.objects.filter(extension=KEY, enabled=True, event__isnull=False):
        value = (config.settings or {}).get("interval_minutes")
        minutes = 10 if value is None or value == "" else int(value)
        if minutes <= 0 or not config.feature_enabled("attendees"):
            continue
        if config.last_sync_at is None or config.last_sync_at + dt.timedelta(minutes=minutes) <= now:
            queue(config, reason="periodic")
            n += 1
    return n


# ------------------------------------------------------------------ check-ins back to pretix
def on_event(event_type: str, payload: Any, event: Any) -> None:
    """Webhook sink: an attendee imported from pretix was checked in at EVAC's scanners → tell pretix (outbox)."""
    if event_type != "access.checked_in" or event is None or not isinstance(payload, dict):
        return
    source = str(payload.get("source") or "")
    if not source.startswith(f"{KEY}:"):
        return
    config = _config(source.split(":", 1)[1])
    if config is None or config.event_id != event.pk or not config.feature_enabled("push_checkins"):
        return
    if not (config.settings or {}).get("checkin_list"):
        return
    outbox.enqueue(CHECKIN_JOB, {"config": str(config.pk), "attendee": payload.get("id"),
                                 "at": payload.get("checked_in_at")}, event=event,
                   key=f"pretix-checkin:{payload.get('id')}")


def handle_checkin(job: Any) -> None:
    import requests

    from apps.access.models import Attendee
    from apps.extensions import services as ext

    config = _config(job.payload["config"])
    a = Attendee.objects.filter(pk=job.payload.get("attendee")).first()
    if config is None or a is None:
        job.result = {"skipped": "gone"}
        return
    s = config.settings or {}
    url = f"{str(s.get('base_url') or '').rstrip('/')}/api/v1/organizers/{s.get('organizer')}/checkinrpc/redeem/"
    try:
        safefetch.check_url(url, allow_private=_allow_private())
    except safefetch.FetchError as exc:
        ext.write_log(config, "error", f"Check-in of {a.name} not sent to pretix: {exc}")
        job.result = {"failed": str(exc)[:300]}
        return
    body = {"secret": a.code, "source_type": "barcode", "lists": [int(s["checkin_list"])], "type": "entry",
            "force": True, "ignore_unpaid": False, "nonce": f"evac-{a.pk}",
            "datetime": job.payload.get("at") or timezone.now().isoformat()}
    r = requests.post(url, json=body, headers=_headers(config), timeout=15, allow_redirects=False)
    if r.status_code >= 500 or r.status_code == 429:
        raise RuntimeError(f"pretix answered {r.status_code}")  # the outbox retries
    try:
        status = r.json().get("status")
    except ValueError:
        status = None
    ok = r.status_code in (200, 201) and status in ("ok", None)
    ext.write_log(config, "info" if ok else "warning", f"Check-in of {a.name} sent to pretix: "
                  f"{r.status_code} {status or ''}".strip())
    job.result = {"status": r.status_code, "pretix": status}


def test_connection(config: Any) -> ConnectionResult:
    try:
        ev = _get(config, f"{_base(config)}/")
        items = _all(config, "/items/")
        lists = _all(config, "/checkinlists/")
    except SyncError as exc:
        return ConnectionResult(False, str(exc))
    admission = [i for i in items if i.get("admission", True)]
    lists_txt = ", ".join(f"{c.get('id')}: {c.get('name')}" for c in lists[:10]) or "–"
    return ConnectionResult(True, _("%(e)s: %(n)s admission products; check-in lists %(l)s. Nothing was imported "
                                    "yet: use “Sync now”.") % {"e": text((ev or {}).get("name")) or "pretix",
                                                               "n": len(admission), "l": lists_txt})


def purge(config: Any) -> None:
    from apps.access.models import Attendee, TicketType

    source = source_of(config)
    Attendee.objects.filter(event=config.event, source=source).delete()
    TicketType.objects.filter(event=config.event, source=source, attendees__isnull=True).delete()
