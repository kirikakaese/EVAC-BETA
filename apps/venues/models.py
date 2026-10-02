# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venues are reusable across events: venue -> building -> floor -> room, plus zones.

Phase 0 models the hierarchy and capacities/accessibility attributes. Floor plans, exits, assembly
points, waypoints and the route graph follow in Phase 3 (see docs/ROADMAP.md).
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.events.models import validate_timezone


class Venue(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    address = models.TextField(blank=True)
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_timezone])
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_permanent = models.BooleanField(_("permanent venue"), default=False,
                                       help_text=_("A club, hall or campus that hosts many events."))

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def evac_scope_chain(self):
        return [("venue", str(self.pk))]


class Building(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="buildings")
    name = models.CharField(max_length=200)
    outdoor = models.BooleanField(_("open-air site"), default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def evac_scope_chain(self):
        return [("venue", str(self.venue_id))]


class Floor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="floors")
    name = models.CharField(max_length=200)
    level = models.SmallIntegerField(default=0, help_text=_("0 = ground floor, negative = basement."))

    class Meta:
        ordering = ["level", "name"]

    def __str__(self):
        return f"{self.building} · {self.name}"

    @property
    def venue_id(self):
        return self.building.venue_id

    def evac_scope_chain(self):
        return [("venue", str(self.building.venue_id))]


class Zone(models.Model):
    """An area used for targeting and evacuation; may span rooms and be outdoor."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="zones")
    name = models.CharField(max_length=200)
    outdoor = models.BooleanField(default=False)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    color = models.CharField(max_length=7, default="#22c55e")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def evac_scope_chain(self):
        return [("venue", str(self.venue_id)), ("zone", str(self.pk))]


class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="rooms")
    floor = models.ForeignKey(Floor, null=True, blank=True, on_delete=models.SET_NULL, related_name="rooms")
    zones = models.ManyToManyField(Zone, blank=True, related_name="rooms")
    name = models.CharField(max_length=200)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    step_free = models.BooleanField(_("step-free access"), default=True)
    has_lift = models.BooleanField(_("lift access"), default=False)
    wheelchair_spaces = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def evac_scope_chain(self):
        chain = [("venue", str(self.venue_id))]
        chain += [("zone", str(z)) for z in self.zones.values_list("pk", flat=True)]
        chain.append(("room", str(self.pk)))
        return chain
