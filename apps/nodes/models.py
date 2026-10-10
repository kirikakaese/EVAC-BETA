# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venue nodes (ADR-0002, ADR-0036).

On **central**: ``Node`` (a registered venue node), ``Checkout`` (an event handed to a node), ``OpLogEntry`` rows
received from nodes, ``ProxiedAction`` (a live action from central's control room waiting for the node).

On a **node** (``EVAC_MODE=node``): ``NodeIdentity`` (its keys and central's address, one row) and ``NodeEvent``
(per event: snapshot version, op-log position); its own changes are ``OpLogEntry`` rows with ``pushed_at``.
"""
from __future__ import annotations

import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class Node(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    #: one-time enrolment code (hashed) until the node enrolled
    code_hash = models.CharField(max_length=64, blank=True)
    code_expires_at = models.DateTimeField(null=True, blank=True)
    sign_public = models.CharField(max_length=64, blank=True)
    box_public = models.CharField(max_length=64, blank=True)
    token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    enrolled_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    version = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def active(self) -> bool:
        return self.enrolled_at is not None and self.revoked_at is None


class Checkout(models.Model):
    class State(models.TextChoices):
        ACTIVE = "active", _("checked out")
        CHECKIN_REQUESTED = "checkin_requested", _("check-in requested")
        CHECKED_IN = "checked_in", _("checked in")
        FORCED = "forced", _("forced check-in")

    OPEN = (State.ACTIVE, State.CHECKIN_REQUESTED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="node_checkouts")
    node = models.ForeignKey(Node, on_delete=models.PROTECT, related_name="checkouts")
    state = models.CharField(max_length=20, choices=State.choices, default=State.ACTIVE)
    started_at = models.DateTimeField(auto_now_add=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    #: highest contiguous op-log ``seq`` central applied
    applied_seq = models.PositiveBigIntegerField(default=0)
    #: the node received the live state once (seed); later snapshots carry configuration only
    seeded = models.BooleanField(default=False)
    snapshot_version = models.CharField(max_length=64, blank=True)  # last version the node confirmed
    last_sync = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [models.UniqueConstraint(fields=["event"], condition=models.Q(state__in=["active",
                                                                                              "checkin_requested"]),
                                               name="nodes_one_open_checkout_per_event")]

    def __str__(self) -> str:
        return f"{self.event} → {self.node} ({self.state})"


class OpLogEntry(models.Model):
    """On a node: one live-state change made here (``upsert``/``delete`` of a row, or an ``audit`` entry), kept
    until central confirmed it."""

    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(db_index=True)
    node_id = models.UUIDField(null=True, blank=True)
    seq = models.PositiveBigIntegerField()
    key = models.CharField(max_length=100)  # idempotency key: "<checkout>:<seq>" (seq restarts per checkout)
    kind = models.CharField(max_length=10)  # upsert | delete | audit
    model = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField()
    pushed_at = models.DateTimeField(null=True, blank=True)  # confirmed by central

    class Meta:
        ordering = ["event_id", "seq"]
        constraints = [models.UniqueConstraint(fields=["key"], name="nodes_oplog_unique_key")]

    def __str__(self) -> str:
        return f"#{self.seq} {self.kind} {self.model}:{self.object_id}"


class ReceivedOp(models.Model):
    """On central: an op-log entry a node sent and central applied (the idempotency record)."""

    id = models.BigAutoField(primary_key=True)
    checkout = models.ForeignKey(Checkout, on_delete=models.CASCADE, related_name="ops")
    seq = models.PositiveBigIntegerField()
    key = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=10)
    model = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField()
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["checkout", "seq"]

    def __str__(self) -> str:
        return f"#{self.seq} {self.kind} {self.model}:{self.object_id}"


class ProxiedAction(models.Model):
    """A live action asked for on central for a checked-out event; the node runs it and answers."""

    class Status(models.TextChoices):
        PENDING = "pending", _("waiting for the node")
        DONE = "done", _("done")
        FAILED = "failed", _("failed")
        EXPIRED = "expired", _("expired")

    id = models.BigAutoField(primary_key=True)
    checkout = models.ForeignKey(Checkout, on_delete=models.CASCADE, related_name="actions")
    kind = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    actor_repr = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.kind} ({self.status})"


class NodeIdentity(models.Model):
    """This node's identity (only on a node; one row)."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    node_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=100, blank=True)
    central_url = models.URLField(blank=True)
    ca_file = models.CharField(max_length=300, blank=True)
    sign_private_encrypted = models.TextField(blank=True)
    box_private_encrypted = models.TextField(blank=True)
    sign_public = models.CharField(max_length=64, blank=True)
    box_public = models.CharField(max_length=64, blank=True)
    token_encrypted = models.TextField(blank=True)
    enrolled_at = models.DateTimeField(null=True, blank=True)
    last_contact = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)

    def __str__(self) -> str:
        return self.name or "node"


class NodeEvent(models.Model):
    """An event this node holds (only on a node)."""

    event_id = models.UUIDField(primary_key=True)
    slug = models.SlugField(max_length=80)
    checkout_id = models.UUIDField(null=True, blank=True)
    checked_out = models.BooleanField(default=True)
    checkin_requested = models.BooleanField(default=False)
    snapshot_version = models.CharField(max_length=64, blank=True)
    snapshot_at = models.DateTimeField(null=True, blank=True)
    seeded = models.BooleanField(default=False)
    next_seq = models.PositiveBigIntegerField(default=1)
    pushed_seq = models.PositiveBigIntegerField(default=0)
    action_after = models.PositiveBigIntegerField(default=0)  # last proxied action id handled
    files_missing = models.PositiveIntegerField(default=0)
    files = models.JSONField(default=list, blank=True)  # [[media path, sha256 or ""], ...] of the last snapshot

    def __str__(self) -> str:
        return self.slug
