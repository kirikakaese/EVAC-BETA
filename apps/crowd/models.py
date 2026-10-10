# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crowd and occupancy (brief §11.4, ADR-0040): how many people are in a room, a zone or any counted area.

Counts come from door staff with the clicker in the staff app (several devices add up, offline clicks are sent
later), from sensors (HTTP API or MQTT) and later from ticket scanners (access module). Every change is a
``CountEvent``; the area keeps the current ``value`` and its ``state`` (normal, busy, full) from the capacity rule.
No personal data: a click records the device's label, never who clicked.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Area(models.Model):
    class State(models.TextChoices):
        NORMAL = "normal", _("Normal")
        BUSY = "busy", _("Busy")
        FULL = "full", _("Full")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="crowd_areas")
    name = models.CharField(_("name"), max_length=120)
    room = models.ForeignKey("venues.Room", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("room"), help_text=_("Screens in this room show “full”."))
    zone = models.ForeignKey("venues.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("zone"), help_text=_("Or a whole zone (screens in the zone)."))
    capacity = models.PositiveIntegerField(_("capacity"), default=0,
                                           help_text=_("People allowed at once. 0: count only, no rule."))
    busy_percent = models.PositiveSmallIntegerField(_("busy from (%)"), default=80)
    full_percent = models.PositiveSmallIntegerField(_("full from (%)"), default=100)
    release_percent = models.PositiveSmallIntegerField(
        _("open again below (%)"), default=90,
        help_text=_("“Full” ends only when the count falls below this, so the sign does not flicker at the limit."))
    show_on_screens = models.BooleanField(_("show “full” on screens"), default=True)
    screen_groups = models.ManyToManyField("screens.ScreenGroup", blank=True, related_name="+",
                                           verbose_name=_("also on screen groups"),
                                           help_text=_("e.g. the foyer screens that send people to the hall."))
    alternative = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                    verbose_name=_("send people to"),
                                    help_text=_("Suggested on the screens while it has space."))
    full_text = models.CharField(_("text when full"), max_length=200, blank=True,
                                 help_text=_("Empty: “{name} is full” and the alternative."))
    notify_roles = models.ManyToManyField("events.Role", blank=True, related_name="+",
                                          verbose_name=_("alert roles"),
                                          help_text=_("Their members get an alert when it is full and when it "
                                                      "opens again."))
    channels = models.JSONField(_("also alert channels"), default=list, blank=True)
    sensor_key = models.SlugField(_("sensor key"), max_length=60, blank=True,
                                  help_text=_("For sensors over MQTT: <prefix>/crowd/<event>/<sensor key>."))
    order = models.IntegerField(_("order"), default=0)
    value = models.IntegerField(default=0)
    state = models.CharField(max_length=6, choices=State.choices, default=State.NORMAL)
    state_since = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["event", "name"], name="crowd_area_name"),
            models.UniqueConstraint(fields=["event", "sensor_key"], condition=~models.Q(sensor_key=""),
                                    name="crowd_area_sensor_key"),
        ]

    def __str__(self):
        return self.name

    @property
    def percent(self) -> int | None:
        return round(self.value * 100 / self.capacity) if self.capacity else None

    @property
    def free(self) -> int | None:
        return max(0, self.capacity - self.value) if self.capacity else None

    def evac_scope_chain(self) -> list[tuple[str, str]]:
        chain: list[tuple[str, str]] = []
        if self.room_id:
            chain.append(("room", str(self.room_id)))
            chain += [("zone", str(z)) for z in self.room.zones.values_list("pk", flat=True)]
        if self.zone_id:
            chain.append(("zone", str(self.zone_id)))
        return chain


class CountEvent(models.Model):
    class Source(models.TextChoices):
        CLICKER = "clicker", _("Door counter")
        SENSOR = "sensor", _("Sensor")
        MQTT = "mqtt", _("Sensor (MQTT)")
        API = "api", _("API")
        SCANNER = "scanner", _("Ticket scanner")
        CORRECTION = "correction", _("Correction")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="counts")
    at = models.DateTimeField(db_index=True)
    delta = models.IntegerField()
    value_after = models.IntegerField()
    source = models.CharField(max_length=12, choices=Source.choices)
    device = models.CharField(max_length=80, blank=True, help_text="door or device label")
    #: only for corrections (who set the number); clicks and sensors stay anonymous
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")
    client_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-at"]
        constraints = [models.UniqueConstraint(fields=["area", "client_id"], condition=~models.Q(client_id=""),
                                               name="crowd_count_client_id")]


class Sample(models.Model):
    """One minute of an area's history: the last value, the highest and the lowest (for the charts)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="samples")
    minute = models.DateTimeField()
    value = models.IntegerField()
    peak = models.IntegerField()
    low = models.IntegerField()

    class Meta:
        ordering = ["minute"]
        constraints = [models.UniqueConstraint(fields=["area", "minute"], name="crowd_sample_minute")]
