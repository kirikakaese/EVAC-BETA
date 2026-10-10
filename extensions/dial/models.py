# SPDX-License-Identifier: AGPL-3.0-or-later
"""DIAL extension data (ADR-0037): broadcasts sent to DIAL, phone recordings received, DECT alerts, role mapping."""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class Broadcast(models.Model):
    """One call to DIAL's emergency or messaging broadcast, sent through the outbox (the delivery report)."""

    class Kind(models.TextChoices):
        EMERGENCY = "emergency", _("Ring handsets (emergency broadcast)")
        MESSAGE = "message", _("DECT text message")

    class Source(models.TextChoices):
        EVACUATION = "evacuation", _("Evacuation")
        ANNOUNCEMENT = "announcement", _("Announcement")
        TEST = "test", _("Test")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")
        SKIPPED = "skipped", _("Skipped")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey("extensions.ExtensionConfig", on_delete=models.CASCADE, related_name="dial_broadcasts")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="dial_broadcasts")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    source = models.CharField(max_length=12, choices=Source.choices)
    reference = models.CharField(max_length=100, blank=True)  # announcement delivery id, evacuation state version
    text = models.TextField()
    group = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    targets = models.PositiveIntegerField(default=0)
    detail = models.CharField(max_length=500, blank=True)
    response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["config", "kind", "source", "reference"],
                                               condition=~models.Q(reference=""), name="dial_broadcast_once")]

    def __str__(self):
        return f"{self.get_kind_display()} {self.created_at:%Y-%m-%d %H:%M}"


class Recording(models.Model):
    """An announcement recorded by phone in DIAL (``announcement.recorded``) and the EVAC announcement made of it."""

    class Status(models.TextChoices):
        RECEIVED = "received", _("Received")
        IMPORTED = "imported", _("Imported")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey("extensions.ExtensionConfig", on_delete=models.CASCADE, related_name="dial_recordings")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="dial_recordings")
    extension = models.CharField(_("DIAL extension"), max_length=40)
    audio = models.CharField(max_length=300, blank=True)  # DIAL media name, empty when DIAL kept the PBX path only
    dial_announcement = models.CharField(max_length=40, blank=True)  # DIAL's announcement id (newer DIAL)
    duration = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED)
    detail = models.CharField(max_length=300, blank=True)
    transcript = models.TextField(blank=True)
    speech_file = models.CharField(max_length=80, blank=True)
    announcement = models.ForeignKey("announcements.Announcement", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-received_at"]


class DectAlert(models.Model):
    """A DECT alert from DIAL (``dect.rfp.down`` / ``rfp.up`` / ``sync.degraded``), kept for the status widget and the
    operations log."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey("extensions.ExtensionConfig", on_delete=models.CASCADE, related_name="dial_dect_alerts")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="dial_dect_alerts")
    kind = models.CharField(max_length=40)
    severity = models.CharField(max_length=10, blank=True)
    message = models.CharField(max_length=500, blank=True)
    rfp = models.CharField(max_length=120, blank=True)
    dial_id = models.CharField(max_length=40, blank=True)
    at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-at"]


class RoleMapping(models.Model):
    """A DIAL event role and the EVAC role its members may be given. Applied by a person, never automatically."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey("extensions.ExtensionConfig", on_delete=models.CASCADE, related_name="dial_roles")
    dial_role = models.CharField(_("DIAL role"), max_length=40)
    role = models.ForeignKey("events.Role", on_delete=models.CASCADE, related_name="+", verbose_name=_("EVAC role"))

    class Meta:
        ordering = ["dial_role"]
        constraints = [models.UniqueConstraint(fields=["config", "dial_role"], name="dial_role_once")]


class Snapshot(models.Model):
    """The last answer of DIAL for a page (DECT status, members), fetched by the outbox, never inside a request."""

    config = models.ForeignKey("extensions.ExtensionConfig", on_delete=models.CASCADE, related_name="dial_snapshots")
    key = models.CharField(max_length=20)
    data = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=300, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["config", "key"], name="dial_snapshot_once")]
