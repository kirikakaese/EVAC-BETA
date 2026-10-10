# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ready-made shift board widgets: one click creates the feeds and custom widgets for screens (ADR-0023)."""
from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _

PRESETS: list[dict[str, Any]] = [
    {"name": "Crew: needed now", "source": "crew.needed_now", "visual": "table", "items": "$.items[*]",
     "fields": {"title": "title", "subtitle": "team", "label": "time", "value": "need"},
     "options": {"heading": "Help needed", "limit": 10}, "poll": 60},
    {"name": "Crew: shift board", "source": "crew.board", "visual": "table", "items": "$.items[*]",
     "fields": {"title": "title", "subtitle": "team", "label": "time", "value": "filled"},
     "options": {"heading": "Shifts", "limit": 20}, "poll": 60},
]


def install(event: Any, *, actor: Any, request: Any = None) -> list[Any]:
    from apps.widgets import services as widgets
    from apps.widgets.models import CustomWidget, Feed

    made = []
    for p in PRESETS:
        if CustomWidget.objects.filter(event=event, name=p["name"]).exists():
            continue
        feed = Feed.objects.filter(event=event, kind=Feed.Kind.SOURCE, source=p["source"]).first()
        if feed is None:
            feed = widgets.save_feed(Feed(event=event, name=_("Crew %(s)s") % {"s": p["source"].split(".", 1)[1]},
                                          kind=Feed.Kind.SOURCE, source=p["source"], poll_seconds=p["poll"]),
                                     actor=actor, request=request)
            widgets.fetch_feed(feed)
        made.append(widgets.save_widget(CustomWidget(event=event, name=p["name"], feed=feed, visual=p["visual"],
                                                     items_path=p["items"], fields=p["fields"],
                                                     options=p["options"]), actor=actor, request=request))
    return made
