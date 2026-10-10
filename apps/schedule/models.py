# SPDX-License-Identifier: AGPL-3.0-or-later
"""The program (brief §11.1, ADR-0038): stages, tracks, speakers, sessions and their live changes.

A session's ``starts_at``/``ends_at`` are its current times; ``planned_start``/``planned_end`` keep what the schedule
said before a delay or a move, so screens can show "was 14:00". Sessions imported from pretalx, frab or iCal carry
their ``source`` and ``external_id``; a field changed here is listed in ``overrides`` and keeps its local value when
the source syncs again.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class Stage(models.Model):
    """A room or stage where sessions take place, optionally the venue room it is in (screens in that room show it)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(_("name"), max_length=120)
    room = models.ForeignKey("venues.Room", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("venue room"))
    order = models.IntegerField(_("order"), default=0)
    source = models.CharField(max_length=80, blank=True)
    external_id = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["order", "name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="schedule_stage_name")]

    def __str__(self):
        return self.name


class Track(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="tracks")
    name = models.CharField(_("name"), max_length=120)
    colour = models.CharField(_("colour"), max_length=7, default="#64748b")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="schedule_track_name")]

    def __str__(self):
        return self.name


class Speaker(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="speakers")
    name = models.CharField(_("name"), max_length=200)
    bio = models.TextField(_("biography"), blank=True)
    source = models.CharField(max_length=80, blank=True)
    external_id = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Session(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        CANCELLED = "cancelled", _("Cancelled")

    #: fields an import writes (and a local change can override)
    IMPORTED = ("title", "subtitle", "abstract", "language", "kind", "stage", "track", "starts_at", "ends_at",
                "speakers", "public", "url", "status")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="sessions")
    title = models.CharField(_("title"), max_length=300)
    subtitle = models.CharField(_("subtitle"), max_length=300, blank=True)
    abstract = models.TextField(_("abstract"), blank=True)
    language = models.CharField(_("language"), max_length=20, blank=True)
    kind = models.CharField(_("type"), max_length=60, blank=True, help_text=_("e.g. talk, workshop, concert"))
    url = models.URLField(_("link"), max_length=500, blank=True)
    stage = models.ForeignKey(Stage, null=True, blank=True, on_delete=models.SET_NULL, related_name="sessions",
                              verbose_name=_("room / stage"))
    track = models.ForeignKey(Track, null=True, blank=True, on_delete=models.SET_NULL, related_name="sessions",
                              verbose_name=_("track"))
    speakers = models.ManyToManyField(Speaker, blank=True, related_name="sessions", verbose_name=_("speakers"))
    starts_at = models.DateTimeField(_("starts"), db_index=True)
    ends_at = models.DateTimeField(_("ends"))
    planned_start = models.DateTimeField(null=True, blank=True)
    planned_end = models.DateTimeField(null=True, blank=True)
    planned_stage = models.ForeignKey(Stage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    note = models.CharField(_("note on screens"), max_length=200, blank=True,
                            help_text=_("Shown with the session, e.g. “Moved to Hall B” or “Starts 15 min late”."))
    public = models.BooleanField(_("public"), default=True)
    source = models.CharField(max_length=80, blank=True)  # "" (made here) or "<extension>:<config id>"
    external_id = models.CharField(max_length=200, blank=True, db_index=True)
    overrides = models.JSONField(default=list, blank=True)  # fields changed here; a re-sync leaves them alone
    missing_upstream = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at", "stage__order", "title"]
        indexes = [models.Index(fields=["event", "starts_at"])]
        constraints = [models.UniqueConstraint(fields=["event", "source", "external_id"],
                                               condition=~models.Q(external_id=""), name="schedule_session_source")]

    def __str__(self):
        return self.title

    @property
    def delay_minutes(self) -> int:
        if self.planned_start is None:
            return 0
        return int((self.starts_at - self.planned_start).total_seconds() // 60)

    @property
    def moved(self) -> bool:
        return self.planned_stage_id is not None and self.planned_stage_id != self.stage_id

    @property
    def changed(self) -> bool:
        return self.status == self.Status.CANCELLED or bool(self.delay_minutes) or self.moved

    def evac_anchor_label(self) -> str:
        return f"{self.title} ({self.stage.name})" if self.stage_id else self.title


class SessionChange(models.Model):
    """A live change (delay, cancellation, room change, new time, restore): the changes ticker and the history."""

    class Kind(models.TextChoices):
        DELAY = "delay", _("Delayed")
        EARLIER = "earlier", _("Earlier")
        CANCEL = "cancel", _("Cancelled")
        ROOM = "room", _("Room changed")
        TIME = "time", _("New time")
        RESTORE = "restore", _("Back to plan")
        NEW = "new", _("Added")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="changes")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="session_changes")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    text = models.CharField(max_length=300)
    data = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-at"]
