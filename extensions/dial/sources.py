# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data sources from DIAL (roadmap 4.4): phonebook, important numbers ("call X for Y"), info pages, DECT status.

They are ordinary data sources (Widgets -> Data feeds -> "Data source"): the widgets module polls them, keeps the
last good snapshot when DIAL is unreachable (offline first) and screens render them with the built-in visuals.
``page.updated`` and ``dect.*`` webhooks refresh the matching feeds at once.
"""
from __future__ import annotations

import html
import re
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from . import link
from .client import Client, DialError, Rejected
from .inbound import REFRESH_JOB

SOURCES = ("dial.phonebook", "dial.numbers", "dial.pages", "dial.dect")
SERVICE_NUMBERS = [("voicemail_number", "Voicemail"), ("echo_test_number", "Echo test"),
                   ("test_ringback_number", "Test ringback"), ("wakeup_service_number", "Wake-up calls"),
                   ("dect_claim_number", "Register a DECT handset"),
                   ("announcement_record_number", "Record an announcement")]


def _client(event: Any) -> tuple[Any, Client]:
    from apps.extensions import services as ext
    from apps.widgets.fetch import FetchError

    config = ext.effective(link.KEY, event)
    if config is None or not config.feature_enabled("data_sources"):
        raise FetchError(_("DIAL is not linked for this event."))
    return config, Client.for_config(config)


def _guard(fn: Any) -> Any:
    def wrapped(event: Any) -> Any:
        from apps.widgets.fetch import FetchError

        try:
            return fn(event)
        except DialError as exc:
            raise FetchError(f"DIAL: {exc}") from None
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


@_guard
def phonebook(event: Any) -> dict[str, Any]:
    _config, client = _client(event)
    data = client.get("phonebook/", event=client.event) or {}
    items = [{"number": e.get("number"), "label": e.get("number_label") or e.get("number"), "name": e.get("name"),
              "type": e.get("type_display") or e.get("type"), "description": e.get("description") or "",
              "location": e.get("location") or "",
              "category": (e.get("category") or {}).get("name", "") if isinstance(e.get("category"), dict) else ""}
             for e in data.get("results") or [] if isinstance(e, dict)]
    return {"event": client.event, "count": len(items), "items": items}


def important(config: Any) -> list[dict[str, str]]:
    """The link's own list: ``number = what for`` per line."""
    out = []
    for line in str(link.settings_of(config).get("important_numbers") or "").splitlines():
        number, sep, what = line.partition("=")
        if sep and number.strip() and what.strip():
            out.append({"number": number.strip()[:20], "label": what.strip()[:120], "kind": "important"})
    return out


@_guard
def numbers(event: Any) -> dict[str, Any]:
    """Important numbers: the link's own list, the emergency numbers (with where they ring) and service numbers."""
    config, client = _client(event)
    items = important(config)
    plan = client.get(f"events/{client.event}/number-plan/") or {}
    targets: dict[str, str] = {}
    try:
        names: dict[str, str] | None = None
        for t in client.results("emergency/targets/", event=client.event):
            if not isinstance(t, dict) or not t.get("number"):
                continue
            label = str(t.get("label") or "")
            dest = re.match(r"Local/([0-9*#]+)@", str(t.get("dial_target") or ""))
            if not label and dest:  # unlabelled target: name the extension it rings
                if names is None:
                    book = client.get("phonebook/", event=client.event) or {}
                    names = {str(e.get("number")): str(e.get("name") or "") for e in book.get("results") or []
                             if isinstance(e, dict)}
                label = names.get(dest.group(1), "")
            targets[str(t["number"])] = label
    except Rejected:
        pass  # the token may lack emergency:read; the numbers still show
    for n in plan.get("emergency_numbers") or []:
        items.append({"number": str(n), "label": targets.get(str(n)) or _("Emergency"), "kind": "emergency"})
    for key, label in SERVICE_NUMBERS:
        if plan.get(key):
            items.append({"number": str(plan[key]), "label": label, "kind": "service"})
    seen, out = set(), []
    for item in items:
        if item["number"] not in seen:
            seen.add(item["number"])
            out.append({**item, "call": _("Call %(n)s") % {"n": item["number"]}})
    return {"event": client.event, "count": len(out), "items": out}


TAG = re.compile(r"<[^>]+>")


def plain(body_html: str) -> str:
    """Text of DIAL's rendered (escaped) Markdown: screens render text, never HTML from another system."""
    text = re.sub(r"</(p|h\d|li|div|tr)>|<br\s*/?>", "\n", body_html or "", flags=re.I)
    text = html.unescape(TAG.sub("", text))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


@_guard
def pages(event: Any) -> dict[str, Any]:
    _config, client = _client(event)
    items = []
    for p in client.results("pages/", event=client.event):
        if not isinstance(p, dict) or not p.get("published", True):
            continue
        items.append({"slug": p.get("slug"), "title": p.get("title"), "text": plain(str(p.get("body_html") or "")),
                      "markdown": p.get("body") or "", "order": p.get("order") or 0,
                      "dashboard": bool(p.get("show_on_dashboard")), "updated_at": p.get("updated_at")})
    items.sort(key=lambda p: (p["order"], str(p["title"] or "")))
    return {"event": client.event, "count": len(items), "items": items}


@_guard
def dect(event: Any) -> dict[str, Any]:
    """RFP and cluster health from DIAL plus the DECT alerts EVAC received."""
    from .models import DectAlert

    config, client = _client(event)
    rfps = [r for r in client.results("dect/rfps/", event__slug=client.event) if isinstance(r, dict)]
    clusters = [c for c in client.results("dect/clusters/", event__slug=client.event) if isinstance(c, dict)]
    counts = {"up": 0, "down": 0, "unsynced": 0, "inactive": 0}
    for r in rfps:
        counts[str(r.get("status") or "inactive")] = counts.get(str(r.get("status") or "inactive"), 0) + 1
    alerts = [{"kind": a.kind, "severity": a.severity, "message": a.message, "rfp": a.rfp, "at": a.at.isoformat()}
              for a in DectAlert.objects.filter(config=config)[:10]]
    return {"event": client.event, "rfps": len(rfps), **counts, "ok": counts["down"] == 0 and counts["unsynced"] == 0,
            "items": [{"name": r.get("name"), "status": r.get("status"), "location": r.get("location") or "",
                       "calls": r.get("active_calls") or 0, "handsets": r.get("handsets") or 0}
                      for r in sorted(rfps, key=lambda r: (r.get("status") == "up", str(r.get("name"))))],
            "clusters": [{"name": c.get("name") or c.get("cluster_id"), "health": c.get("health")} for c in clusters],
            "alerts": alerts, "checked_at": timezone.now().isoformat()}


FETCHERS = {"dial.phonebook": phonebook, "dial.numbers": numbers, "dial.pages": pages, "dial.dect": dect}


def refresh(event: Any, keys: list[str]) -> int:
    """Fetch the event's feeds of these sources now (after a DIAL webhook)."""
    from apps.core import modules

    if not modules.is_enabled("widgets", event):
        return 0
    from apps.widgets import services as widgets
    from apps.widgets.models import Feed

    n = 0
    for feed in Feed.objects.filter(event=event, kind=Feed.Kind.SOURCE, source__in=keys, enabled=True):
        widgets.fetch_feed(feed)
        n += 1
    return n


SNAPSHOT_MAX_AGE = 300


def take_snapshot(config: Any, key: str) -> Any:
    """Fetch ``dect`` (status) or ``members`` (DIAL event members) and keep the answer for the pages."""
    from apps.widgets.fetch import FetchError

    from . import roles
    from .models import Snapshot

    snap, _created = Snapshot.objects.get_or_create(config=config, key=key)
    try:
        snap.data = dect(config.event) if key == "dect" else {"items": roles.fetch_members(config)}
        snap.error = ""
    except (DialError, FetchError) as exc:
        snap.error = str(exc)[:300]
    snap.fetched_at = timezone.now()
    snap.save()
    return snap


def snapshot(config: Any, key: str) -> Any:
    """The stored snapshot; asks the outbox for a fresh one when it is missing or older than five minutes."""
    from apps.core import outbox

    from .models import Snapshot

    snap = Snapshot.objects.filter(config=config, key=key).first()
    stale = snap is None or snap.fetched_at is None or (timezone.now() - snap.fetched_at).total_seconds() > \
        SNAPSHOT_MAX_AGE
    if stale:
        bucket = int(timezone.now().timestamp() // 60)
        outbox.enqueue(REFRESH_JOB, {"config": str(config.pk), "snapshots": [key]}, event=config.event,
                       key=f"dial-snapshot:{config.pk}:{key}:{bucket}")
    return snap


def handle_refresh(job: Any) -> None:
    from apps.extensions.models import ExtensionConfig

    config = ExtensionConfig.objects.select_related("event").filter(pk=job.payload["config"]).first()
    if config is None or config.event is None:
        job.result = {"skipped": "gone"}
        return
    for key in job.payload.get("snapshots") or []:
        take_snapshot(config, key)
    job.result = {"feeds": refresh(config.event, list(job.payload.get("sources") or []))}
