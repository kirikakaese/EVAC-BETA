# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core import crypto


class WebhookEndpoint(models.Model):
    """An outbound receiver. Deliveries are signed with ``X-EVAC-Signature: sha256=<HMAC(body)>``."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey("extensions.ExtensionConfig", on_delete=models.CASCADE, related_name="webhook_endpoints")
    name = models.CharField(max_length=120)
    url = models.URLField(max_length=500)
    secret_encrypted = models.TextField()
    event_types = models.JSONField(default=list, blank=True, help_text=_("Empty = every event type."))
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_delivery_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def secret(self) -> str:
        return crypto.decrypt(self.secret_encrypted)

    def wants(self, event_type: str) -> bool:
        return self.active and (not self.event_types or event_type in self.event_types)


class DeliveryAttempt(models.Model):
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name="attempts")
    delivery_id = models.CharField(max_length=64, db_index=True)
    event_type = models.CharField(max_length=100)
    ok = models.BooleanField(default=False)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class InboundEvent(models.Model):
    """A verified inbound webhook call (kept for inspection; other modules react via a signal)."""

    config = models.ForeignKey("extensions.ExtensionConfig", on_delete=models.CASCADE, related_name="inbound_events")
    event_type = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-received_at"]
