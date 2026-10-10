# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persisted evacuation state (ADR-0029): one row per event and per zone, plus an append-only history."""
from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from . import machine

STATE_CHOICES = [
    (machine.State.NORMAL.value, _("Normal")),
    (machine.State.STAFF_ALERT.value, _("Staff alert")),
    (machine.State.ATTENTION.value, _("Attention")),
    (machine.State.SHELTER.value, _("Shelter in place")),
    (machine.State.EVACUATE.value, _("Evacuate")),
    (machine.State.ALL_CLEAR.value, _("All clear")),
]
KIND_CHOICES = [(k.value, k.value.replace("_", " ")) for k in machine.Kind]


class EvacState(models.Model):
    """The current status of an event (``zone`` empty) or of one zone. Rows are never deleted by a timeout."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_states")
    zone = models.ForeignKey("venues.Zone", null=True, blank=True, on_delete=models.CASCADE,
                             related_name="evac_states")
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=machine.State.NORMAL.value)
    drill = models.BooleanField(default=False)
    since = models.DateTimeField(null=True, blank=True)
    clear_until = models.DateTimeField(null=True, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    source = models.CharField(max_length=40, blank=True)
    reason = models.CharField(max_length=300, blank=True)
    #: bumped on every change; screens and clients use it to order updates
    version = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "zone"], name="evac_state_event_zone"),
            models.UniqueConstraint(fields=["event"], condition=models.Q(zone__isnull=True),
                                    name="evac_state_event"),
        ]

    def __str__(self) -> str:
        where = self.zone.name if self.zone_id else str(_("whole event"))
        return f"{where}: {self.state}{' (drill)' if self.drill else ''}"

    @property
    def status(self) -> machine.Status:
        return machine.Status(machine.State(self.state), self.drill, self.since, self.clear_until)

    def apply(self, status: machine.Status) -> None:
        self.state, self.drill = status.state.value, status.drill
        self.since, self.clear_until = status.since, status.clear_until
        self.version += 1

    def evac_scope_chain(self) -> list[tuple[str, str]] | None:
        return self.zone.evac_scope_chain() if self.zone_id else None


class StateChange(models.Model):
    """Append-only history of every change (also in the audit log, with the drill flag)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_changes")
    zone = models.ForeignKey("venues.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    zone_name = models.CharField(max_length=200, blank=True)
    at = models.DateTimeField()
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    from_state = models.CharField(max_length=20, choices=STATE_CHOICES)
    from_drill = models.BooleanField(default=False)
    to_state = models.CharField(max_length=20, choices=STATE_CHOICES)
    drill = models.BooleanField(default=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    actor_repr = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=40, blank=True)
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["event", "-at"])]

    def __str__(self) -> str:
        return f"{self.at:%H:%M:%S} {self.zone_name or 'event'} {self.from_state} -> {self.to_state}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValueError("evacuation history is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise ValueError("evacuation history is append-only")


class BlockedPoint(models.Model):
    """An exit, assembly point or passage that is not usable during this event (blocked live); routes avoid it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_blocked")
    point = models.ForeignKey("venues.Point", on_delete=models.CASCADE, related_name="+")
    since = models.DateTimeField()
    blocked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "point"], name="evac_blocked_event_point")]

    def __str__(self) -> str:
        return f"{self.point} blocked"

    def evac_scope_chain(self) -> list[tuple[str, str]]:
        chain: list[tuple[str, str]] = self.point.evac_scope_chain()
        return chain


SOURCE_MAX = 40


class EvacPolicy(models.Model):
    """What a trigger source does for a stage (empty: all) in a zone (empty: all), ADR-0031."""

    ACTIONS = [("execute", _("Execute at once")), ("arm", _("Arm: the control room confirms")),
               ("notify", _("Only notify the control room"))]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_policies")
    source = models.CharField(max_length=SOURCE_MAX)
    state = models.CharField(max_length=20, blank=True, choices=STATE_CHOICES)
    zone = models.ForeignKey("venues.Zone", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    action = models.CharField(max_length=10, choices=ACTIONS)
    #: arm only: execute after this many seconds without an answer; empty = wait for a person
    escalate_seconds = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["source", "state"]
        constraints = [models.UniqueConstraint(fields=["event", "source", "state", "zone"],
                                               name="evac_policy_unique")]

    def __str__(self) -> str:
        return f"{self.source}/{self.state or '*'}/{self.zone or '*'}: {self.action}"


class EvacRequest(models.Model):
    """An alarm waiting for the control room (``arm``) or for a second person (``second``)."""

    KINDS = [("arm", _("Waiting for the control room")), ("second", _("Waiting for a second person"))]
    STATUSES = [("pending", _("pending")), ("executed", _("executed at once")), ("confirmed", _("confirmed")),
                ("rejected", _("rejected")),
                ("escalated", _("escalated")), ("expired", _("expired")), ("notified", _("notified")),
                ("superseded", _("superseded"))]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_requests")
    kind = models.CharField(max_length=10, choices=KINDS)
    source = models.CharField(max_length=SOURCE_MAX)
    state = models.CharField(max_length=20, choices=STATE_CHOICES)
    drill = models.BooleanField(default=False)
    zone = models.ForeignKey("venues.Zone", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    reason = models.CharField(max_length=300, blank=True)
    #: event-wide all clear: the zones to clear as well (None: every zone in alarm)
    clear_zones = models.JSONField(null=True, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    requested_repr = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField()
    deadline = models.DateTimeField(null=True, blank=True)
    escalate_seconds = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    #: idempotency key of API/bridge triggers: a repeated delivery returns the same request
    key = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "key"], condition=~models.Q(key=""),
                                               name="evac_request_key")]
        indexes = [models.Index(fields=["status", "deadline"])]

    def __str__(self) -> str:
        return f"{self.source}: {self.state} ({self.status})"

    def evac_scope_chain(self) -> list[tuple[str, str]] | None:
        chain: list[tuple[str, str]] | None = self.zone.evac_scope_chain() if self.zone_id else None
        return chain


class ScheduledDrill(models.Model):
    """A drill that starts by itself at a set time (source ``schedule``). Like every drill it ends with the all
    clear given by a person; a real alarm ends it at once."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_drills")
    at = models.DateTimeField()
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="evacuate")
    zone = models.ForeignKey("venues.Zone", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    started_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["at"]

    def __str__(self) -> str:
        return f"Drill {self.state} at {self.at:%Y-%m-%d %H:%M}"
