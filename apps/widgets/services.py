# SPDX-License-Identifier: AGPL-3.0-or-later
"""Feeds and custom widgets: saving (audited), fetching into snapshots, mapping rows, data for screens."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import crypto, settings_store
from apps.core.audit import log
from apps.core.registry import registry

from . import fetch, mapping, parse
from .models import CustomWidget, Feed

MIN_POLL = 60
MAX_SNAPSHOT = 1_000_000  # characters of JSON


# ------------------------------------------------------------------ feeds
def allow_private() -> bool:
    return bool(settings_store.get("widgets").get("allow_private_networks"))


def sources() -> dict[str, Any]:
    """Data sources registered by modules and extensions (``r.data_source``) that have a fetch function."""
    return {k: s for k, s in registry.ensure_loaded().data_sources.items() if s.fetch is not None}


def source_choices(event) -> list[tuple[str, str]]:
    from apps.core import modules

    return [(k, s.name) for k, s in sources().items() if s.module == "core" or modules.is_enabled(s.module, event)]


def validate_feed(feed: Feed) -> None:
    if feed.kind == Feed.Kind.SOURCE:
        if feed.source not in dict(source_choices(feed.event)):
            raise ValidationError(_("Choose a data source."))
        feed.url = ""
    else:
        if not feed.url:
            raise ValidationError(_("A URL is needed."))
        try:
            fetch.check_url(feed.url, allow_private=allow_private())
        except fetch.FetchError as exc:
            raise ValidationError(str(exc)) from None
        feed.source = ""
    feed.poll_seconds = max(MIN_POLL, min(int(feed.poll_seconds or 300), 86400))


def save_feed(feed: Feed, *, actor, request=None, auth_header: str | None = None) -> Feed:
    validate_feed(feed)
    created = feed._state.adding
    if auth_header is not None:
        feed.auth_header_encrypted = crypto.encrypt(auth_header.strip()) if auth_header.strip() else ""
    feed.save()
    log(action="widgets.feed_created" if created else "widgets.feed_edited", actor=actor, target=feed,
        event=feed.event, request=request, message=f"Data feed {feed.name}",
        changes={"kind": feed.kind, "url": feed.url, "source": feed.source,
                 **({"auth_header": "changed"} if auth_header is not None else {})})
    return feed


def delete_feed(feed: Feed, *, actor, request=None) -> None:
    if feed.widgets.exists():
        raise ValidationError(_("Widgets use this feed; delete them first."))
    log(action="widgets.feed_deleted", actor=actor, target=feed, event=feed.event, request=request,
        message=f"Data feed {feed.name} deleted")
    feed.delete()


def _headers(feed: Feed) -> dict[str, str]:
    if not feed.auth_header_encrypted:
        return {}
    name, _sep, value = crypto.decrypt(feed.auth_header_encrypted).partition(":")
    return {name.strip(): value.strip()} if value.strip() else {"Authorization": name.strip()}


def _jsonable(data: Any) -> Any:
    return json.loads(json.dumps(data, default=str))


def fetch_feed(feed: Feed, *, now: dt.datetime | None = None) -> bool:
    """Fetch once and store the snapshot; returns True when the data changed. Errors are recorded on the feed
    (the last good snapshot stays)."""
    now = now or timezone.now()
    try:
        if feed.kind == Feed.Kind.SOURCE:
            spec = sources().get(feed.source)
            if spec is None:
                raise fetch.FetchError(_("The data source is not available."))
            data = _jsonable(spec.fetch(feed.event))
            etag = ""
        else:
            got = fetch.get(feed.url, headers=_headers(feed), etag=feed.etag, allow_private=allow_private())
            if got.status == 304:
                Feed.objects.filter(pk=feed.pk).update(last_fetch_at=now, last_success_at=now, status="ok", error="")
                return False
            data = parse.parse(feed.kind, got.body)
            etag = got.etag[:200]
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        if len(raw) > MAX_SNAPSHOT:
            raise fetch.FetchError(_("The data is too large (at most 1 MB as JSON)."))
    except (fetch.FetchError, parse.ParseError) as exc:
        Feed.objects.filter(pk=feed.pk).update(last_fetch_at=now, status="error", error=str(exc)[:500])
        feed.status, feed.error = "error", str(exc)[:500]
        return False
    digest = hashlib.sha256(raw.encode()).hexdigest()
    changed = digest != feed.snapshot_hash
    Feed.objects.filter(pk=feed.pk).update(last_fetch_at=now, last_success_at=now, status="ok", error="",
                                           snapshot=data, snapshot_hash=digest, etag=etag)
    feed.snapshot, feed.snapshot_hash, feed.status, feed.error = data, digest, "ok", ""
    if changed and feed.widgets.exists():
        notify_screens(feed.event)
    return changed


def fetch_due(now: dt.datetime | None = None) -> int:
    """Beat task: fetch every enabled feed whose refresh interval has passed."""
    now = now or timezone.now()
    n = 0
    for feed in Feed.objects.filter(enabled=True).select_related("event"):
        if feed.last_fetch_at is None or feed.last_fetch_at + dt.timedelta(seconds=feed.poll_seconds) <= now:
            fetch_feed(feed, now=now)
            n += 1
    return n


def notify_screens(event) -> None:
    from apps.screens import channel
    from apps.screens.models import Screen

    def send():
        for screen in Screen.objects.paired().filter(event=event):
            channel.send(screen, "data.changed", {})
    transaction.on_commit(send)


# ------------------------------------------------------------------ widgets
def validate_widget(w: CustomWidget) -> None:
    try:
        mapping.tokens(w.items_path or "$")
        for path in (w.fields or {}).values():
            mapping.tokens(path or "$")
    except mapping.PathError as exc:
        raise ValidationError(str(exc)) from None
    unknown = set(w.fields or {}) - set(mapping.FIELDS)
    if unknown:
        raise ValidationError(_("Unknown field: %(f)s") % {"f": ", ".join(sorted(unknown))})
    if w.feed.event_id != w.event_id:
        raise ValidationError(_("The feed belongs to another event."))


def save_widget(w: CustomWidget, *, actor, request=None) -> CustomWidget:
    validate_widget(w)
    created = w._state.adding
    w.save()
    log(action="widgets.widget_created" if created else "widgets.widget_edited", actor=actor, target=w,
        event=w.event, request=request, message=f"Custom widget {w.name}",
        changes={"feed": w.feed.name, "visual": w.visual, "items": w.items_path, "fields": w.fields})
    notify_screens(w.event)
    return w


def delete_widget(w: CustomWidget, *, actor, request=None) -> None:
    log(action="widgets.widget_deleted", actor=actor, target=w, event=w.event, request=request,
        message=f"Custom widget {w.name} deleted")
    w.delete()
    notify_screens(w.event)


def widget_rows(w: CustomWidget, now: dt.datetime | None = None) -> list[dict[str, Any]]:
    if w.feed.snapshot is None:
        return []
    opts = w.options or {}
    try:
        return mapping.rows(w.feed.snapshot, w.items_path, w.fields, limit=int(opts.get("limit") or 20),
                            upcoming=bool(opts.get("upcoming")), now=now)
    except mapping.PathError:
        return []


def widget_payload(w: CustomWidget, now: dt.datetime | None = None) -> dict[str, Any]:
    """What a screen needs for one widget: its visual, options and the current rows."""
    feed = w.feed
    stale = feed.status == "error" or feed.last_success_at is None or (
        (now or timezone.now()) - feed.last_success_at > dt.timedelta(seconds=feed.poll_seconds * 3 + 60))
    return {"id": str(w.pk), "name": w.name, "visual": w.visual, "options": w.options or {},
            "rows": widget_rows(w, now), "updated": feed.last_success_at.isoformat() if feed.last_success_at else None,
            "stale": stale}


def event_payload(event, now: dt.datetime | None = None) -> dict[str, Any]:
    return {str(w.pk): widget_payload(w, now)
            for w in CustomWidget.objects.filter(event=event).select_related("feed")}


def editor_choices(event) -> list[dict[str, str]]:
    return [{"value": str(w.pk), "label": w.name, "visual": w.visual}
            for w in CustomWidget.objects.filter(event=event)]
