# SPDX-License-Identifier: AGPL-3.0-or-later
"""Heartbeat data (ADR-0052): the last known status of everything a health check watches (to detect changes), the
Celery pulse, and operator check-ins with their escalations. Kept per installation: a venue node watches what it
runs itself, so nothing here is synced."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

STATUS_CHOICES = [("ok", _("OK")), ("warn", _("Degraded")), ("down", _("Down")), ("unknown", _("Unknown"))]


class HealthState(models.Model):
    """The confirmed status of one item of a health check (``event`` None: the instance-wide view).

    ``status`` changes only after the observed status differed for the grace period (``candidate`` since
    ``candidate_since``), so a flapping link does not alert on every blip. ``alerted``: a "down" alert went out for
    the current outage, so its recovery is reported too."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="heartbeat_states")
    check_key = models.CharField(max_length=64)
    item = models.CharField(max_length=200)
    label = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default="unknown")
    since = models.DateTimeField()
    candidate = models.CharField(max_length=8, blank=True)
    candidate_since = models.DateTimeField(null=True, blank=True)
    detail = models.CharField(max_length=500, blank=True)
    url = models.CharField(max_length=500, blank=True)
    checked_at = models.DateTimeField()
    alerted = models.BooleanField(default=False)

    class Meta:
        ordering = ["check_key", "label"]
        constraints = [
            models.UniqueConstraint(fields=["event", "check_key", "item"], name="heartbeat_state_once"),
            models.UniqueConstraint(fields=["check_key", "item"], condition=models.Q(event__isnull=True),
                                    name="heartbeat_state_once_instance"),
        ]

    def __str__(self) -> str:
        return f"{self.check_key}:{self.item} {self.status}"


class Pulse(models.Model):
    """A timestamp written by a periodic task (``celery``: the heartbeat task ran, so worker and beat work)."""

    key = models.CharField(max_length=64, primary_key=True)
    at = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.key} {self.at:%H:%M:%S}"


class CheckIn(models.Model):
    """“I'm here”: an operator confirmed they are at their post."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="heartbeat_checkins")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")
    user_repr = models.CharField(max_length=200, blank=True)
    at = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=20, blank=True)  # page | dashboard | staff

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.user_repr} {self.at:%Y-%m-%d %H:%M}"


class CheckInWatch(models.Model):
    """Per event: since when check-ins are required. Set when check-ins become active and cleared when they stop, so
    switching them on or going live never escalates at once."""

    event = models.OneToOneField("events.Event", primary_key=True, on_delete=models.CASCADE,
                                 related_name="heartbeat_watch")
    armed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.event_id} armed {self.armed_at}"


class CheckInEscalation(models.Model):
    """One step for one missed check-in (step 0: a reminder to the people who check in; step n: the n-th role of the
    escalation chain). Unique per due time and step, so each step runs once."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="heartbeat_escalations")
    due_at = models.DateTimeField()
    step = models.PositiveSmallIntegerField()
    roles = models.JSONField(default=list, blank=True)
    recipients = models.PositiveIntegerField(default=0)
    channels = models.JSONField(default=list, blank=True)
    at = models.DateTimeField()

    class Meta:
        ordering = ["-at"]
        constraints = [models.UniqueConstraint(fields=["event", "due_at", "step"], name="heartbeat_escalation_once")]

    def __str__(self) -> str:
        return f"{self.event_id} {self.due_at:%H:%M} step {self.step}"
