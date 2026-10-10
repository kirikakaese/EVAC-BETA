# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ready-made DIAL widgets (roadmap 4.4): one click creates the data feeds and custom widgets below. They are
ordinary feeds and widgets afterwards (Widgets module), editable and usable in any layout."""
from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _

PRESETS: list[dict[str, Any]] = [
    {"name": "DIAL: call X for Y", "source": "dial.numbers", "visual": "cards", "items": "$.items[*]",
     "fields": {"title": "call", "subtitle": "label"}, "options": {"heading": "Phone numbers", "limit": 8},
     "poll": 900},
    {"name": "DIAL: important numbers", "source": "dial.numbers", "visual": "table", "items": "$.items[*]",
     "fields": {"title": "label", "value": "number"}, "options": {"heading": "Important numbers", "limit": 20},
     "poll": 900},
    {"name": "DIAL: phonebook", "source": "dial.phonebook", "visual": "table", "items": "$.items[*]",
     "fields": {"title": "name", "value": "label", "subtitle": "location"},
     "options": {"heading": "Phonebook", "limit": 30}, "poll": 900},
    {"name": "DIAL: info pages", "source": "dial.pages", "visual": "cards", "items": "$.items[*]",
     "fields": {"title": "title", "subtitle": "text"}, "options": {"heading": "Info", "limit": 6}, "poll": 1800},
    {"name": "DIAL: DECT status", "source": "dial.dect", "visual": "list", "items": "$.items[*]",
     "fields": {"title": "name", "value": "status", "subtitle": "location"},
     "options": {"heading": "DECT network", "limit": 20}, "poll": 120},
]


def install(event: Any, *, actor: Any, request: Any = None) -> list[Any]:
    """Create the feeds and widgets that do not exist yet (by name). Returns the widgets created."""
    from apps.widgets import services as widgets
    from apps.widgets.models import CustomWidget, Feed

    made = []
    for p in PRESETS:
        if CustomWidget.objects.filter(event=event, name=p["name"]).exists():
            continue
        feed = Feed.objects.filter(event=event, kind=Feed.Kind.SOURCE, source=p["source"]).first()
        if feed is None:
            feed = widgets.save_feed(Feed(event=event, name=_("DIAL %(s)s") % {"s": p["source"].split(".", 1)[1]},
                                          kind=Feed.Kind.SOURCE, source=p["source"], poll_seconds=p["poll"]),
                                     actor=actor, request=request)
            widgets.fetch_feed(feed)
        made.append(widgets.save_widget(CustomWidget(event=event, name=p["name"], feed=feed, visual=p["visual"],
                                                     items_path=p["items"], fields=p["fields"],
                                                     options=p["options"]), actor=actor, request=request))
    return made
