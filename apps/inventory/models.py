# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resources and inventory (brief §11.6, ADR-0042): radios, keys, vehicles, tools, laptops … with an asset tag and
a printable QR label, lend and return (with a signature or photo), who has what, due-back reminders, maintenance
notes and a place on the venue map.

The QR label holds the URL of the item's page (``/e/<event>/inventory/t/<asset tag>/``): staff scan it with the
phone camera and lend or return it there.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="inventory_categories")
    name = models.CharField(_("name"), max_length=80)
    loan_hours = models.PositiveIntegerField(_("usual loan (hours)"), default=0,
                                             help_text=_("Suggested due time when lending. 0: no due time."))

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="inventory_category_name")]

    def __str__(self):
        return self.name


def _photo_path(instance: models.Model, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()[:5] if "." in filename else "jpg"
    event_id = getattr(instance, "event_id", None) or instance.item.event_id  # type: ignore[attr-defined]
    return f"inventory/{event_id}/{uuid.uuid4().hex}.{ext}"


class Item(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", _("Available")
        LENT = "lent", _("Lent")
        MAINTENANCE = "maintenance", _("Maintenance")
        MISSING = "missing", _("Missing")
        RETIRED = "retired", _("Retired")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="inventory_items")
    name = models.CharField(_("name"), max_length=120)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="items",
                                 verbose_name=_("category"))
    asset_tag = models.CharField(_("asset tag"), max_length=40, help_text=_("Empty: the next free number."))
    serial = models.CharField(_("serial number"), max_length=80, blank=True)
    description = models.TextField(_("description"), blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.AVAILABLE)
    room = models.ForeignKey("venues.Room", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("kept in"))
    location = models.CharField(_("where exactly"), max_length=120, blank=True, help_text=_("e.g. Shelf B3"))
    photo = models.ImageField(upload_to=_photo_path, blank=True, verbose_name=_("photo"))
    floor = models.ForeignKey("venues.Floor", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    position_x = models.FloatField(null=True, blank=True)
    position_y = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["asset_tag"]
        constraints = [models.UniqueConstraint(fields=["event", "asset_tag"], name="inventory_item_tag")]

    def __str__(self):
        return f"{self.asset_tag} {self.name}"


class Loan(models.Model):
    class Condition(models.TextChoices):
        OK = "ok", _("OK")
        DAMAGED = "damaged", _("Damaged")
        INCOMPLETE = "incomplete", _("Incomplete")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="loans")
    borrower = models.CharField(_("lent to"), max_length=120)
    borrower_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="+", verbose_name=_("account"))
    contact = models.CharField(_("contact"), max_length=120, blank=True, help_text=_("Phone, DECT or team."))
    lent_at = models.DateTimeField()
    due_at = models.DateTimeField(_("due back"), null=True, blank=True)
    lent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+")
    signature = models.ImageField(upload_to=_photo_path, blank=True)
    photo_out = models.ImageField(upload_to=_photo_path, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    condition = models.CharField(max_length=10, choices=Condition.choices, blank=True)
    photo_back = models.ImageField(upload_to=_photo_path, blank=True)
    notes = models.TextField(blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-lent_at"]

    @property
    def is_open(self) -> bool:
        return self.returned_at is None


class Note(models.Model):
    class Kind(models.TextChoices):
        NOTE = "note", _("Note")
        MAINTENANCE = "maintenance", _("Maintenance")
        DAMAGE = "damage", _("Damage")
        STATUS = "status", _("Status")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="notes")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.NOTE)
    text = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at"]
