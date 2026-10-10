# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crew and shifts (brief §11.2, ADR-0041): teams with leads, crew members ("angels") with skills, shift types,
shifts with the headcount and skills they need, and who works them.

A crew member may have an EVAC account (then they sign up for shifts themselves in the staff app) or not (imported
from Engelsystem, or entered by a team lead). Every shift has a check-in token: its QR code hangs at the shift's
place, crew scan it with the phone camera to check in and out.
"""
from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def _token() -> str:
    return secrets.token_urlsafe(12)


class Skill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="crew_skills")
    name = models.CharField(_("name"), max_length=80, help_text=_("e.g. First aid, Forklift"))

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="crew_skill_name")]

    def __str__(self):
        return self.name


class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="crew_teams")
    name = models.CharField(_("name"), max_length=80)
    description = models.TextField(_("description"), blank=True)
    colour = models.CharField(_("colour"), max_length=7, default="#2563eb")
    leads = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+",
                                   verbose_name=_("team leads"))
    meeting_point = models.CharField(_("meeting point"), max_length=120, blank=True,
                                     help_text=_("Where the team meets, used in crew calls."))
    source = models.CharField(max_length=60, blank=True)
    external_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="crew_team_name")]

    def __str__(self):
        return self.name

    def evac_scope_chain(self) -> list[tuple[str, str]]:
        return [("team", str(self.pk))]


class Member(models.Model):
    """A crew member of the event, with or without an EVAC account."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="crew_members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="crew_memberships", verbose_name=_("account"))
    name = models.CharField(_("name"), max_length=120)
    contact = models.CharField(_("contact"), max_length=120, blank=True, help_text=_("Phone or DECT number."))
    teams = models.ManyToManyField(Team, blank=True, related_name="members", verbose_name=_("teams"))
    skills = models.ManyToManyField(Skill, blank=True, related_name="members", verbose_name=_("skills"))
    arrived = models.BooleanField(_("arrived"), default=False)
    notes = models.TextField(_("notes"), blank=True)
    source = models.CharField(max_length=60, blank=True)
    external_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["event", "user"], condition=models.Q(user__isnull=False),
                                               name="crew_member_user")]

    def __str__(self):
        return self.name

    def evac_scope_chain(self) -> list[tuple[str, str]]:
        return [("team", str(t)) for t in self.teams.values_list("pk", flat=True)]


class ShiftType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="crew_shift_types")
    name = models.CharField(_("name"), max_length=80)
    description = models.TextField(_("description"), blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="crew_shifttype_name")]

    def __str__(self):
        return self.name


class Shift(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="crew_shifts")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="shifts", verbose_name=_("team"))
    shift_type = models.ForeignKey(ShiftType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                   verbose_name=_("type"))
    title = models.CharField(_("title"), max_length=150)
    room = models.ForeignKey("venues.Room", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("room"))
    location = models.CharField(_("where"), max_length=150, blank=True)
    starts_at = models.DateTimeField(_("starts"))
    ends_at = models.DateTimeField(_("ends"))
    needed = models.PositiveSmallIntegerField(_("people needed"), default=1)
    skills = models.ManyToManyField(Skill, blank=True, related_name="+", verbose_name=_("skills needed"))
    notes = models.TextField(_("notes"), blank=True)
    open_signup = models.BooleanField(_("open for sign-up"), default=True,
                                      help_text=_("Crew can sign up themselves in the staff app."))
    checkin_token = models.CharField(max_length=40, default=_token, unique=True, editable=False)
    source = models.CharField(max_length=60, blank=True)
    external_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["starts_at", "team__name"]
        indexes = [models.Index(fields=["event", "starts_at"])]

    def __str__(self):
        return self.title

    def evac_scope_chain(self) -> list[tuple[str, str]]:
        return [("team", str(self.team_id))]

    @property
    def place(self) -> str:
        return self.room.name if self.room_id else self.location

    @property
    def hours(self) -> float:
        return (self.ends_at - self.starts_at).total_seconds() / 3600


class Assignment(models.Model):
    class Status(models.TextChoices):
        SIGNED_UP = "signed_up", _("Signed up")
        CHECKED_IN = "checked_in", _("Checked in")
        DONE = "done", _("Done")
        NO_SHOW = "no_show", _("No-show")

    ACTIVE = (Status.SIGNED_UP, Status.CHECKED_IN, Status.DONE)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="assignments")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="assignments")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SIGNED_UP)
    signed_up_at = models.DateTimeField(auto_now_add=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                           related_name="+")
    source = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["shift__starts_at"]
        constraints = [models.UniqueConstraint(fields=["shift", "member"], name="crew_assignment_once")]

    def evac_scope_chain(self) -> list[tuple[str, str]]:
        return [("team", str(self.shift.team_id))]
