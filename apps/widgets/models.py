# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data feeds and custom widgets (ADR-0023).

A :class:`Feed` is where data comes from: a URL (JSON, RSS/Atom, iCal, CSV) fetched on the server, or a data
source a module registers. Its last good result is kept as a snapshot, so screens keep showing data when the
source is down. A :class:`CustomWidget` maps the snapshot to rows (JSONPath subset) and picks a visual; layouts
place it with a "data" element.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Feed(TimeStampedModel):
    class Kind(models.TextChoices):
        JSON = "json", _("JSON (HTTP)")
        RSS = "rss", _("RSS or Atom feed")
        ICAL = "ical", _("iCal calendar")
        CSV = "csv", _("CSV (e.g. a spreadsheet export)")
        SOURCE = "source", _("EVAC data source")

    class Status(models.TextChoices):
        NEW = "", _("Not fetched yet")
        OK = "ok", _("OK")
        ERROR = "error", _("Error")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="data_feeds")
    name = models.CharField(_("name"), max_length=120)
    kind = models.CharField(_("type"), max_length=10, choices=Kind.choices, default=Kind.JSON)
    url = models.URLField(_("URL"), max_length=1000, blank=True)
    source = models.CharField(_("data source"), max_length=80, blank=True)
    auth_header_encrypted = models.TextField(blank=True)  # e.g. "Authorization: Bearer …", never shown again
    poll_seconds = models.PositiveIntegerField(_("refresh every (seconds)"), default=300)
    enabled = models.BooleanField(_("enabled"), default=True)
    status = models.CharField(max_length=10, choices=Status.choices, blank=True, default="")
    error = models.CharField(max_length=500, blank=True)
    last_fetch_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    snapshot = models.JSONField(null=True, blank=True)
    snapshot_hash = models.CharField(max_length=64, blank=True)
    etag = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CustomWidget(TimeStampedModel):
    class Visual(models.TextChoices):
        TEXT = "text", _("Text")
        LIST = "list", _("List")
        TABLE = "table", _("Table")
        CARDS = "cards", _("Cards")
        COUNTER = "counter", _("Counter")
        GAUGE = "gauge", _("Gauge")
        TICKER = "ticker", _("Ticker")
        BARS = "bars", _("Bar chart")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="custom_widgets")
    name = models.CharField(_("name"), max_length=120)
    feed = models.ForeignKey(Feed, on_delete=models.PROTECT, related_name="widgets", verbose_name=_("feed"))
    items_path = models.CharField(_("items"), max_length=300, default="$",
                                  help_text=_("JSONPath of the list of items, e.g. $.items or $.data[*]. $: the "
                                              "whole result."))
    fields = models.JSONField(default=dict, blank=True)  # {"title": "name", "value": "count", ...}
    visual = models.CharField(_("visual"), max_length=10, choices=Visual.choices, default=Visual.LIST)
    options = models.JSONField(default=dict, blank=True)  # limit, template, unit, min, max, upcoming, ...

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
