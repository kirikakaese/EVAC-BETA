# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ticketing and access (brief §11.5, ADR-0044): ticket types, attendees with a ticket code, access zones with
scanner rules, presence per zone and every scan.

A ticket type grants zones (``zones``); a zone that is ``open_to_all`` admits every valid ticket. Scanner
stations scan *into* or *out of* a zone; the first scan into a zone marked ``checkin`` checks the attendee in.
Scans made offline arrive later with their ``client_id`` and the time on the device; a replay changes nothing.
"""
from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def new_code() -> str:
    """A ticket code for EVAC's own attendees (12 characters, URL-safe)."""
    return secrets.token_urlsafe(9)


class AccessZone(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="access_zones")
    name = models.CharField(_("name"), max_length=80, help_text=_("e.g. Main entrance, Backstage, Crew area"))
    open_to_all = models.BooleanField(_("every valid ticket"), default=False,
                                      help_text=_("Off: only the ticket types that grant this zone."))
    checkin = models.BooleanField(_("checks in"), default=False,
                                  help_text=_("The first scan into this zone checks the attendee in (the entrance)."))
    reentry = models.BooleanField(_("re-entry allowed"), default=True,
                                  help_text=_("Off: a ticket that is already inside is refused."))
    room = models.ForeignKey("venues.Room", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("room"))
    area_id = models.UUIDField(_("occupancy area"), null=True, blank=True,
                               help_text=_("Scans in and out count people in this occupancy area."))
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="access_zone_name")]

    def __str__(self):
        return self.name

    def evac_scope_chain(self) -> list[tuple[str, str]]:
        return [("access_zone", str(self.pk))]


class TicketType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="ticket_types")
    name = models.CharField(_("name"), max_length=80, help_text=_("e.g. Day ticket, Crew, Artist"))
    colour = models.CharField(_("colour"), max_length=7, default="#2563eb",
                              help_text=_("Wristband or badge colour."))
    zones = models.ManyToManyField(AccessZone, blank=True, related_name="ticket_types",
                                   verbose_name=_("grants zones"))
    badge_layout = models.ForeignKey("content.Layout", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+", verbose_name=_("badge layout"),
                                     help_text=_("Empty: the built-in badge."))
    source = models.CharField(max_length=60, blank=True)
    external_id = models.CharField(max_length=100, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Attendee(models.Model):
    class Status(models.TextChoices):
        VALID = "valid", _("Valid")
        CANCELLED = "cancelled", _("Cancelled")
        BLOCKED = "blocked", _("Blocked")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="attendees")
    name = models.CharField(_("name"), max_length=150)
    email = models.EmailField(_("e-mail"), blank=True)
    company = models.CharField(_("organisation"), max_length=150, blank=True)
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT, related_name="attendees",
                                    verbose_name=_("ticket type"))
    code = models.CharField(_("ticket code"), max_length=128, help_text=_("Empty: a new random code."))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.VALID)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    badge_printed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    source = models.CharField(max_length=60, blank=True)
    external_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["event", "code"], name="access_attendee_code")]

    def __str__(self):
        return self.name

    @property
    def is_valid(self) -> bool:
        return self.status == self.Status.VALID


class Presence(models.Model):
    """Whether an attendee is inside a zone (the last accepted scan there)."""

    attendee = models.ForeignKey(Attendee, on_delete=models.CASCADE, related_name="presence")
    zone = models.ForeignKey(AccessZone, on_delete=models.CASCADE, related_name="presence")
    inside = models.BooleanField(default=False)
    since = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attendee", "zone"], name="access_presence")]


class Scan(models.Model):
    class Direction(models.TextChoices):
        IN = "in", _("In")
        OUT = "out", _("Out")

    class Result(models.TextChoices):
        OK = "ok", _("OK")
        DENIED = "denied", _("Not allowed")
        DUPLICATE = "duplicate", _("Already inside")
        INVALID = "invalid", _("Cancelled or blocked")
        UNKNOWN = "unknown", _("Unknown ticket")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="scans")
    zone = models.ForeignKey(AccessZone, on_delete=models.CASCADE, related_name="scans")
    attendee = models.ForeignKey(Attendee, null=True, blank=True, on_delete=models.SET_NULL, related_name="scans")
    code_hint = models.CharField(max_length=8, blank=True, help_text="The last characters of an unknown code.")
    direction = models.CharField(max_length=3, choices=Direction.choices, default=Direction.IN)
    result = models.CharField(max_length=10, choices=Result.choices)
    at = models.DateTimeField(help_text="When it was scanned (the device's time for offline scans).")
    received_at = models.DateTimeField(auto_now_add=True)
    offline = models.BooleanField(default=False)
    device = models.CharField(max_length=80, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")
    client_id = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["-at"]
        constraints = [models.UniqueConstraint(fields=["event", "client_id"], condition=~models.Q(client_id=""),
                                               name="access_scan_client_id")]
        indexes = [models.Index(fields=["zone", "-at"])]
