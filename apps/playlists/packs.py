# SPDX-License-Identifier: AGPL-3.0-or-later
"""Playlists in ``.evacpack`` files (ADR-0024): a playlist with its layouts is a "screen pack". Schedules and
overrides are not packed (they target this event's screens and times)."""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from . import services
from .models import Playlist, PlaylistItem


def choices(event) -> list[tuple[str, str]]:
    return [(str(pk), name) for pk, name in Playlist.objects.filter(event=event).values_list("pk", "name")]


def requires(event, ids: set[str]) -> dict[str, set[str]]:
    items = PlaylistItem.objects.filter(playlist__event=event, playlist_id__in=ids)
    return {"layouts": {str(i) for i in items.exclude(layout=None).values_list("layout_id", flat=True)},
            "playlists": {str(i) for i in items.exclude(child=None).values_list("child_id", flat=True)}}


def dump(event, ids: set[str], files) -> list[dict[str, Any]]:
    rows = {str(p.pk): p for p in Playlist.objects.filter(event=event, pk__in=ids).prefetch_related("items")}
    ordered: list[Playlist] = []

    def visit(pk: str, seen: frozenset[str] = frozenset()) -> None:  # nested playlists first
        pl = rows.get(pk)
        if pl is None or pl in ordered or pk in seen:
            return
        for item in pl.items.all():
            if item.child_id:
                visit(str(item.child_id), seen | {pk})
        ordered.append(pl)

    for pk in sorted(rows, key=lambda k: rows[k].name):
        visit(pk)
    return [{"id": str(pl.pk), "name": pl.name, "description": pl.description, "mode": pl.mode,
             "default_duration": pl.default_duration,
             "items": [{"layout": str(i.layout_id) if i.layout_id else None,
                        "child": str(i.child_id) if i.child_id else None, "duration": i.duration, "weight": i.weight,
                        "tags": i.tags, "condition": i.condition, "enabled": i.enabled} for i in pl.items.all()]}
            for pl in ordered]


def _name(event, base: str) -> str:
    value, n = base[:200], 2
    while Playlist.objects.filter(event=event, name=value).exists():
        value = f"{base[:190]} ({n})"
        n += 1
    return value


def load(event, items: list[dict[str, Any]], ctx) -> list[str]:
    from apps.content.models import Layout

    created = []
    for item in items:
        mode = item.get("mode") if item.get("mode") in Playlist.Mode.values else Playlist.Mode.ORDERED
        pl = services.save_playlist(
            Playlist(event=event, name=_name(event, str(item.get("name") or _("Imported playlist"))),
                     description=str(item.get("description") or "")[:2000], mode=mode,
                     default_duration=max(1, min(int(item.get("default_duration") or 10), 86400))),
            actor=ctx.actor, request=ctx.request)
        ctx.ids[str(item["id"])] = str(pl.pk)
        for entry in item.get("items") or []:
            layout = Layout.objects.filter(event=event, pk=ctx.ids.get(str(entry.get("layout")))).first() \
                if entry.get("layout") else None
            child = Playlist.objects.filter(event=event, pk=ctx.ids.get(str(entry.get("child")))).first() \
                if entry.get("child") else None
            if not layout and not child:
                ctx.warn(_("Playlist %(name)s: an item was skipped (its layout is not in the pack).")
                         % {"name": pl.name})
                continue
            try:
                services.save_item(PlaylistItem(
                    playlist=pl, layout=layout, child=child, duration=entry.get("duration") or None,
                    weight=max(1, min(int(entry.get("weight") or 1), 100)),
                    tags=[str(t)[:64] for t in entry.get("tags") or []][:20],
                    condition=str(entry.get("condition") or "")[:300], enabled=bool(entry.get("enabled", True))),
                    actor=ctx.actor, request=ctx.request)
            except (ValidationError, TypeError, ValueError) as exc:
                ctx.warn(_("Playlist %(name)s: an item was skipped (%(error)s).")
                         % {"name": pl.name, "error": "; ".join(getattr(exc, "messages", [str(exc)]))[:200]})
        created.append(pl.name)
    return created
