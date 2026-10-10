# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venues are reusable across events: venue -> building -> floor -> room, plus zones.

Exits, assembly points, doors, waypoints, stairs and lifts are ``Point`` rows placed on a floor (x/y in metres
in that floor's plan); ``Edge`` rows connect them into the route graph (ADR-0026, ``routing.py``). Floor plans
and georeferencing come with the map editor.
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
    #: floor plan (map editor, ADR-0027): "<sha256>.png|svg" under MEDIA_ROOT/venues/plans/, size in pixels
    plan_file = models.CharField(max_length=80, blank=True)
    plan_width = models.PositiveIntegerField(default=0)
    plan_height = models.PositiveIntegerField(default=0)
    #: metres per plan pixel; ``plan_scaled`` is False until someone measured a known distance
    metres_per_px = models.FloatField(default=0.05)
    plan_scaled = models.BooleanField(default=False)
    #: georeference (ADR-0028): latitude/longitude of the plan's top-left corner and the bearing of the plan's
    #: "up" (degrees clockwise from north); empty until aligned with the map
    geo_lat = models.FloatField(null=True, blank=True)
    geo_lon = models.FloatField(null=True, blank=True)
    geo_rotation = models.FloatField(default=0)

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
    #: outlines drawn in the map editor: [{"floor": "<id>" | null, "points": [[x, y], ...]}] in metres
    areas = models.JSONField(default=list, blank=True)

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


class Point(models.Model):
    """A node of the route graph: an exit, an assembly point, a door, a waypoint, stairs or a lift."""

    class Kind(models.TextChoices):
        WAYPOINT = "waypoint", _("Waypoint")
        DOOR = "door", _("Door")
        STAIRS = "stairs", _("Stairs")
        LIFT = "lift", _("Lift")
        EXIT = "exit", _("Exit")
        ASSEMBLY = "assembly", _("Assembly point")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="points")
    floor = models.ForeignKey(Floor, null=True, blank=True, on_delete=models.SET_NULL, related_name="points",
                              help_text=_("Empty: outdoors at ground level."))
    zone = models.ForeignKey(Zone, null=True, blank=True, on_delete=models.SET_NULL, related_name="points")
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="points")
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.WAYPOINT)
    name = models.CharField(_("name"), max_length=200)
    x = models.FloatField(_("x (m)"), default=0, help_text=_("Metres from the left edge of the floor plan."))
    y = models.FloatField(_("y (m)"), default=0, help_text=_("Metres from the top edge of the floor plan."))
    capacity = models.PositiveIntegerField(
        _("capacity"), null=True, blank=True,
        help_text=_("Exits: people per minute; assembly points: people. Informational for now."))
    step_free = models.BooleanField(_("step-free"), default=True,
                                    help_text=_("Usable with a wheelchair (stairs usually are not)."))
    note = models.CharField(_("note"), max_length=300, blank=True)

    class Meta:
        ordering = ["kind", "name"]
        indexes = [models.Index(fields=["venue", "kind"])]

    def __str__(self):
        return f"{self.get_kind_display()} {self.name}"

    @property
    def level(self) -> int:
        return self.floor.level if self.floor_id else 0

    def evac_scope_chain(self):
        chain = [("venue", str(self.venue_id))]
        if self.zone_id:
            chain.append(("zone", str(self.zone_id)))
        if self.kind == self.Kind.ASSEMBLY:
            chain.append(("assembly", str(self.pk)))
        return chain


class Edge(models.Model):
    """A walkable connection between two points of the same venue."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="edges")
    a = models.ForeignKey(Point, on_delete=models.CASCADE, related_name="edges_out", verbose_name=_("from"))
    b = models.ForeignKey(Point, on_delete=models.CASCADE, related_name="edges_in", verbose_name=_("to"))
    one_way = models.BooleanField(_("one way"), default=False,
                                  help_text=_("Only from the first to the second point (e.g. an exit-only door)."))
    length_m = models.FloatField(_("length (m)"), null=True, blank=True,
                                 help_text=_("Empty: the straight distance (plus 5 m per floor)."))
    step_free = models.BooleanField(_("step-free"), default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["a", "b"], name="venues_edge_unique_pair"),
                       models.CheckConstraint(condition=~models.Q(a=models.F("b")), name="venues_edge_not_loop")]

    def __str__(self):
        arrow = "→" if self.one_way else "↔"
        return f"{self.a.name} {arrow} {self.b.name}"

    def evac_scope_chain(self):
        return [("venue", str(self.venue_id))]
