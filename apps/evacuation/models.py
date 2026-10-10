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


class Bridge(models.Model):
    """A hardware trigger bridge (Raspberry Pi GPIO, ESP32) of an event, ADR-0032.

    ``inputs``: ``[{"key": "in1", "label": "Fire panel relay 3", "state": "evacuate", "zone": "<uuid>|"}]``.
    ``status``: the last reported state per input (``rest``/``active``/``fault``) plus firmware/uptime.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_bridges")
    name = models.CharField(max_length=100)
    token_hash = models.CharField(max_length=64, unique=True)
    token_prefix = models.CharField(max_length=16)
    inputs = models.JSONField(default=list, blank=True)
    status = models.JSONField(default=dict, blank=True)
    online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    transport = models.CharField(max_length=10, blank=True)  # https | mqtt
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return str(self.name)

    def input(self, key: str) -> dict[str, Any] | None:
        return next((i for i in self.inputs if i.get("key") == key), None)


SOUNDS = [("siren", _("Siren")), ("gong", _("Gong")), ("alert", _("Alert tone")), ("none", _("No sound"))]


class StageContent(models.Model):
    """What screens show and play in a stage (ADR-0033). Without a layout the built-in fallback is used."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_content")
    state = models.CharField(max_length=20, choices=STATE_CHOICES)
    #: a content layout (no foreign key: the content module may be off or not installed)
    layout_id = models.UUIDField(null=True, blank=True)
    texts = models.JSONField(default=list, blank=True)
    rotate_seconds = models.PositiveIntegerField(default=8)
    pictograms_only = models.BooleanField(default=False)
    sound = models.CharField(max_length=10, choices=SOUNDS, default="none")
    sound_every = models.PositiveIntegerField(default=30)
    speech_text = models.CharField(max_length=500, blank=True)
    speech_file = models.CharField(max_length=100, blank=True)
    speech_status = models.CharField(max_length=10, blank=True)  # "", pending, ready, failed
    speech_detail = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "state"], name="evac_content_event_state")]

    def __str__(self) -> str:
        return f"{self.state} content"


class EventAlarm(models.Model):
    """Per-event alarm counter and signing key (ADR-0003, ADR-0034): ``seq`` orders every message to screens."""

    event = models.OneToOneField("events.Event", on_delete=models.CASCADE, primary_key=True, related_name="evac_alarm")
    seq = models.PositiveBigIntegerField(default=0)
    seq_at = models.DateTimeField(null=True, blank=True)  # when ``seq`` was last bumped (watchdog)
    watchdog_seq = models.PositiveBigIntegerField(default=0)  # the last message the watchdog alerted about
    public_key = models.CharField(max_length=100, blank=True)
    private_key_encrypted = models.TextField(blank=True)
    previous_public_key = models.CharField(max_length=100, blank=True)
    previous_valid_until = models.DateTimeField(null=True, blank=True)
    key_created_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"alarm #{self.seq}"


class ScreenAck(models.Model):
    """The latest evacuation payload a screen confirmed it rendered (roadmap 3.8): one row per screen."""

    screen_id = models.UUIDField(primary_key=True)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_screen_acks")
    seq = models.PositiveBigIntegerField(default=0)
    version = models.CharField(max_length=32, blank=True)
    state = models.CharField(max_length=20, blank=True)
    drill = models.BooleanField(default=False)
    via = models.CharField(max_length=20, blank=True)  # websocket | sse | poll | fetch | fallback
    rendered_at = models.DateTimeField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now=True)
    fallback = models.BooleanField(default=False)  # rendered the built-in fallback layout
    detail = models.CharField(max_length=200, blank=True)
    #: readiness (roadmap 3.9): the bundle version last served to the screen, and its last self-test
    bundle_served = models.CharField(max_length=16, blank=True)
    bundle_served_at = models.DateTimeField(null=True, blank=True)
    selftest = models.JSONField(default=dict, blank=True)
    selftest_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.screen_id} rendered {self.state} #{self.seq}"


class LatencySample(models.Model):
    """Trigger-to-render time of one screen for one change (for the p95 shown to the control room)."""

    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="+")
    seq = models.PositiveBigIntegerField()
    screen_id = models.UUIDField()
    latency_ms = models.PositiveIntegerField()
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["seq", "screen_id", "event"], name="evac_latency_once")]
        indexes = [models.Index(fields=["event", "-at"])]


class StaffAck(models.Model):
    """A staff member's answer to an alarm in the staff app: "I'm on it", "zone clear", "need help"."""

    KINDS = [("on_it", _("I'm on it")), ("zone_clear", _("Zone clear")), ("need_help", _("Need help"))]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="evac_staff_acks")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    user_repr = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=KINDS)
    zone = models.ForeignKey("venues.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    seq = models.PositiveBigIntegerField(default=0)  # the alarm message it answers
    drill = models.BooleanField(default=False)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.user_repr}: {self.kind}"
