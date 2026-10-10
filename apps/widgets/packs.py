# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data feeds and custom widgets in ``.evacpack`` files (ADR-0024). Feeds travel without their authorization
header (a secret) and without fetched data: the importing server fetches them itself."""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from . import services
from .models import CustomWidget, Feed


def _errors(exc: ValidationError) -> str:
    return "; ".join(str(m) for m in exc.messages)[:300]


def feed_choices(event) -> list[tuple[str, str]]:
    return [(str(pk), name) for pk, name in Feed.objects.filter(event=event).values_list("pk", "name")]


def dump_feeds(event, ids: set[str], files) -> list[dict[str, Any]]:
    return [{"id": str(f.pk), "name": f.name, "kind": f.kind, "url": f.url, "source": f.source,
             "poll_seconds": f.poll_seconds, "enabled": f.enabled, "needs_auth": bool(f.auth_header_encrypted)}
            for f in Feed.objects.filter(event=event, pk__in=ids).order_by("name")]


def load_feeds(event, items: list[dict[str, Any]], ctx) -> list[str]:
    from .tasks import fetch_feed

    created = []
    for item in items:
        name = str(item.get("name") or "")[:120] or _("Imported feed")
        kind = item.get("kind") if item.get("kind") in Feed.Kind.values else Feed.Kind.JSON
        feed = Feed(event=event, name=name, kind=kind, url=str(item.get("url") or "")[:1000],
                    source=str(item.get("source") or "")[:80], enabled=bool(item.get("enabled", True)),
                    poll_seconds=int(item.get("poll_seconds") or 300))
        try:
            services.save_feed(feed, actor=ctx.actor, request=ctx.request)
        except ValidationError as exc:
            ctx.warn(_("Feed %(name)s skipped: %(error)s") % {"name": name, "error": _errors(exc)})
            continue
        if item.get("needs_auth"):
            ctx.warn(_("Feed %(name)s needs an authorization header: add it on the feed page.") % {"name": name})
        ctx.ids[str(item["id"])] = str(feed.pk)
        pk = str(feed.pk)
        transaction.on_commit(lambda pk=pk: fetch_feed.delay(pk))
        created.append(name)
    return created


def widget_choices(event) -> list[tuple[str, str]]:
    return [(str(pk), name) for pk, name in CustomWidget.objects.filter(event=event).values_list("pk", "name")]


def widget_requires(event, ids: set[str]) -> dict[str, set[str]]:
    return {"feeds": {str(f) for f in CustomWidget.objects.filter(event=event, pk__in=ids)
                      .values_list("feed_id", flat=True)}}


def dump_widgets(event, ids: set[str], files) -> list[dict[str, Any]]:
    return [{"id": str(w.pk), "name": w.name, "feed": str(w.feed_id), "items_path": w.items_path,
             "fields": w.fields, "visual": w.visual, "options": w.options}
            for w in CustomWidget.objects.filter(event=event, pk__in=ids).order_by("name")]


def load_widgets(event, items: list[dict[str, Any]], ctx) -> list[str]:
    created = []
    for item in items:
        name = str(item.get("name") or "")[:120] or _("Imported widget")
        feed = Feed.objects.filter(event=event, pk=ctx.ids.get(str(item.get("feed")))).first()
        if feed is None:
            ctx.warn(_("Widget %(name)s skipped: its feed was not imported.") % {"name": name})
            continue
        w = CustomWidget(event=event, name=name, feed=feed, items_path=str(item.get("items_path") or "$")[:300],
                         fields=item.get("fields") if isinstance(item.get("fields"), dict) else {},
                         visual=item.get("visual") if item.get("visual") in CustomWidget.Visual.values
                         else CustomWidget.Visual.LIST,
                         options=item.get("options") if isinstance(item.get("options"), dict) else {})
        try:
            services.save_widget(w, actor=ctx.actor, request=ctx.request)
        except ValidationError as exc:
            ctx.warn(_("Widget %(name)s skipped: %(error)s") % {"name": name, "error": _errors(exc)})
            continue
        ctx.ids[str(item["id"])] = str(w.pk)
        created.append(name)
    return created
