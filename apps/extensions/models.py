# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stored configuration of extensions (instance-wide rows have ``event=None``)."""
from __future__ import annotations

import uuid

from django.conf import settings as django_settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core import crypto


class ExtensionConfig(models.Model):
    class Health(models.TextChoices):
        UNKNOWN = "unknown", _("Not tested")
        OK = "ok", _("OK")
        ERROR = "error", _("Error")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    extension = models.CharField(max_length=64, db_index=True)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="extension_configs")
    enabled = models.BooleanField(default=False)
    use_instance = models.BooleanField(
        default=False, help_text=_("Event rows only: use the instance-wide connection instead of an own one."))
    settings = models.JSONField(default=dict, blank=True)
    secrets_encrypted = models.TextField(blank=True)
    features = models.JSONField(default=dict, blank=True)
    webhook_secret_encrypted = models.TextField(blank=True)
    health = models.CharField(max_length=10, choices=Health.choices, default=Health.UNKNOWN)
    last_check_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["extension", "event"], name="uniq_extension_event"),
            models.UniqueConstraint(fields=["extension"], condition=models.Q(event__isnull=True),
                                    name="uniq_extension_instance"),
        ]

    def __str__(self):
        return f"{self.extension}@{self.event.slug if self.event_id else 'instance'}"

    @property
    def is_saved(self) -> bool:
        """The primary key is a client-side UUID, so ``pk`` is set before the row exists."""
        return not self._state.adding

    @property
    def spec(self):
        from apps.core.registry import registry

        return registry.get_extension(self.extension)

    # secrets ------------------------------------------------------------
    @property
    def secrets(self) -> dict:
        return crypto.decrypt_json(self.secrets_encrypted)

    def set_secrets(self, values: dict) -> None:
        self.secrets_encrypted = crypto.encrypt_json({k: v for k, v in values.items() if v})

    def secret(self, name: str, default: str = "") -> str:
        return self.secrets.get(name, default)

    @property
    def webhook_secret(self) -> str:
        return crypto.decrypt(self.webhook_secret_encrypted)

    def feature_enabled(self, key: str) -> bool:
        spec = self.spec
        default = True
        if spec is not None:
            default = next((f.default_enabled for f in spec.features if f.key == key), False)
        return bool(self.enabled and self.features.get(key, default))

    @property
    def status(self) -> str:
        if not self.enabled:
            return "disabled"
        if self.health == self.Health.ERROR:
            return "error"
        return "enabled"


class ExtensionLog(models.Model):
    class Level(models.TextChoices):
        INFO = "info", _("Info")
        WARN = "warn", _("Warning")
        ERROR = "error", _("Error")

    config = models.ForeignKey(ExtensionConfig, on_delete=models.CASCADE, related_name="logs")
    level = models.CharField(max_length=8, choices=Level.choices, default=Level.INFO)
    message = models.CharField(max_length=500)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class InboundDelivery(models.Model):
    """Idempotency record for inbound webhooks: the same delivery id is processed once."""

    config = models.ForeignKey(ExtensionConfig, on_delete=models.CASCADE, related_name="inbound_deliveries")
    delivery_id = models.CharField(max_length=200)
    event_type = models.CharField(max_length=100, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    status = models.PositiveSmallIntegerField(default=200)
    response = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["config", "delivery_id"], name="uniq_inbound_delivery")]
