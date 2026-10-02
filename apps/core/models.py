# SPDX-License-Identifier: AGPL-3.0-or-later
"""Core models shared by every EVAC app: audit log, module states, settings values, outbox, notifications."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# --------------------------------------------------------------------------- audit log

class ImmutableError(Exception):
    """Raised on any attempt to change or delete audit rows."""


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableError("audit log rows are immutable")

    def delete(self):
        raise ImmutableError("audit log rows are immutable")

    def for_event(self, event):
        return self.filter(event_id=event.pk)


class AuditLog(models.Model):
    """Append-only, hash-chained record of every state-changing action.

    Actor and event are stored as plain ids plus a human-readable copy (no foreign keys): deleting a user
    or event must never rewrite audit rows (that would break the chain and is blocked by a database
    trigger on PostgreSQL). Write rows only through :func:`apps.core.audit.log`.
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_repr = models.CharField(max_length=200, blank=True)
    event_id = models.UUIDField(null=True, blank=True, db_index=True)
    event_repr = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    target_repr = models.CharField(max_length=300, blank=True)
    scope = models.JSONField(default=dict, blank=True)
    message = models.CharField(max_length=500, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    drill = models.BooleanField(default=False, help_text=_("Action happened as part of a drill."))
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    objects = AuditQuerySet.as_manager()

    HASHED_FIELDS = ("created_at", "actor_id", "actor_repr", "event_id", "event_repr", "action", "target_type",
                     "target_id", "target_repr", "scope", "message", "changes", "ip_address", "drill")

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["target_type", "target_id"]), models.Index(fields=["event_id", "-id"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.actor_repr or 'system'} {self.action} {self.target_repr}"

    def payload(self) -> dict:
        data = {}
        for name in self.HASHED_FIELDS:
            value = getattr(self, name)
            if name == "created_at":
                value = value.isoformat(timespec="microseconds")
            elif name in ("actor_id", "event_id") and value is not None:
                value = str(value)
            data[name] = value
        return data

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableError("audit log rows are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableError("audit log rows are immutable")


class AuditChainHead(models.Model):
    """Single row holding the hash of the newest audit entry; locked while appending."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_hash = models.CharField(max_length=64)
    count = models.BigIntegerField(default=0)


# --------------------------------------------------------------------------- modules

class ModuleState(models.Model):
    """Instance-wide on/off state of a module (absent row = the module's default)."""

    key = models.CharField(max_length=64, unique=True)
    enabled = models.BooleanField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    def __str__(self):
        return f"{self.key}={'on' if self.enabled else 'off'}"


class EventModuleState(models.Model):
    """Per-event override of a module's state (absent row = follow the instance state)."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="module_states")
    key = models.CharField(max_length=64)
    enabled = models.BooleanField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "key"], name="uniq_event_module")]

    def __str__(self):
        return f"{self.event_id}:{self.key}={'on' if self.enabled else 'off'}"


# --------------------------------------------------------------------------- settings

class SettingValue(models.Model):
    """Values of one settings namespace at one scope level (only the keys set at that level)."""

    namespace = models.CharField(max_length=64)
    level = models.CharField(max_length=20)
    scope_id = models.CharField(max_length=64, blank=True, help_text=_("Object id; empty for instance level."))
    values = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["namespace", "level", "scope_id"], name="uniq_setting_scope")]

    def __str__(self):
        return f"{self.namespace}@{self.level}:{self.scope_id or '-'}"


# --------------------------------------------------------------------------- outbox

class OutboxJob(models.Model):
    """Durable outbox for outgoing deliveries (webhooks, notifications, external APIs).

    Rows are written in the same transaction as the change that caused them, delivered by the worker
    (``apps.core.tasks.drain_outbox``) with exponential backoff, and never lost on a crash.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        DONE = "done", _("Delivered")
        FAILED = "failed", _("Failed, will retry")
        DEAD = "dead", _("Gave up")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=64, db_index=True)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="outbox_jobs")
    payload = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_error = models.TextField(blank=True)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.kind} {self.status} ({self.attempts})"


# --------------------------------------------------------------------------- notifications

class Notification(models.Model):
    """In-app notification shown under the bell in the top bar."""

    class Level(models.TextChoices):
        INFO = "info", _("Info")
        OK = "ok", _("Success")
        WARN = "warn", _("Warning")
        ERR = "err", _("Error")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="notifications")
    level = models.CharField(max_length=8, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
