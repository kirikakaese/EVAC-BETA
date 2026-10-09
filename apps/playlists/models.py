# SPDX-License-Identifier: AGPL-3.0-or-later
"""What screens play when: playlists, schedule rules and live overrides (brief §5.6, ADR-0016).

Priority order (highest wins): evacuation > emergency override > live override > urgent override > schedule >
default playlist. The server sends every screen its **program** (entries with time windows plus the playlists
they use); the player picks the active entry and the current slide itself with the synchronised clock, so it
keeps changing slides offline and all screens change at the same moment.
"""
from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

#: priority bands; evacuation (phase 3) is always the highest and cannot be chosen here
PRIORITY_DEFAULT = 0
PRIORITY_SCHEDULE = 100
PRIORITY_EVACUATION = 1000


class Playlist(TimeStampedModel):
    class Mode(models.TextChoices):
        ORDERED = "ordered", _("In order")
        SHUFFLE = "shuffle", _("Shuffled (same order on every screen)")
        WEIGHTED = "weighted", _("Weighted (items with more weight come more often)")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="playlists")
    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    mode = models.CharField(_("order"), max_length=10, choices=Mode.choices, default=Mode.ORDERED)
    default_duration = models.PositiveIntegerField(
        _("seconds per slide"), default=10,
        help_text=_("Used when neither the item nor the layout sets a duration."))
    is_default = models.BooleanField(_("default playlist of the event"), default=False,
                                     help_text=_("Plays when no schedule or override applies."))
    updated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="playlists_playlist_unique_name")]

    def __str__(self):
        return self.name


class PlaylistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveIntegerField(default=0)
    layout = models.ForeignKey("content.Layout", null=True, blank=True, on_delete=models.CASCADE, related_name="+",
                               verbose_name=_("layout"))
    child = models.ForeignKey(Playlist, null=True, blank=True, on_delete=models.CASCADE, related_name="used_in",
                              verbose_name=_("nested playlist"))
    duration = models.PositiveIntegerField(_("seconds"), null=True, blank=True,
                                           help_text=_("Empty: the layout's own duration or the playlist default."))
    weight = models.PositiveSmallIntegerField(_("weight"), default=1,
                                              help_text=_("Weighted playlists: 3 means three times as often as 1."))
    tags = models.JSONField(_("only on screens tagged"), default=list, blank=True)
    condition = models.CharField(_("show only if"), max_length=300, blank=True,
                                 help_text=_('e.g. screen.zone == "North" or not screen.room'))
    valid_from = models.DateTimeField(_("from"), null=True, blank=True)
    valid_until = models.DateTimeField(_("until"), null=True, blank=True)
    enabled = models.BooleanField(_("enabled"), default=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return str(self.layout or self.child or "?")

    def clean(self):
        if bool(self.layout_id) == bool(self.child_id):
            raise ValidationError(_("Choose either a layout or a nested playlist."))
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValidationError({"valid_until": _("Must be after the start.")})


class Targeted(models.Model):
    """Which screens something applies to: everything, screen groups and/or single screens."""

    all_screens = models.BooleanField(_("all screens"), default=False)
    groups = models.ManyToManyField("screens.ScreenGroup", blank=True, related_name="+",
                                    verbose_name=_("screen groups"))
    screens = models.ManyToManyField("screens.Screen", blank=True, related_name="+", verbose_name=_("screens"))

    class Meta:
        abstract = True

    def target_label(self) -> str:
        if self.all_screens:
            return str(_("All screens"))
        names = [g.name for g in self.groups.all()] + [s.name for s in self.screens.all()]
        return ", ".join(names) or str(_("No screens"))

    def applies_to(self, screen, group_ids: set) -> bool:
        if self.all_screens:
            return True
        return (any(g.pk in group_ids for g in self.groups.all())
                or any(s.pk == screen.pk for s in self.screens.all()))


class Content(models.Model):
    """What is shown: a layout or a playlist."""

    layout = models.ForeignKey("content.Layout", null=True, blank=True, on_delete=models.CASCADE, related_name="+",
                               verbose_name=_("layout"))
    playlist = models.ForeignKey(Playlist, null=True, blank=True, on_delete=models.CASCADE, related_name="+",
                                 verbose_name=_("playlist"))

    class Meta:
        abstract = True

    def content_ref(self) -> dict:
        if self.playlist_id:
            return {"playlist": str(self.playlist_id)}
        if self.layout_id:
            return {"layout": str(self.layout_id)}
        return {"message": str(self.pk)}

    def content_label(self) -> str:
        return str(self.playlist or self.layout or "")


class ScheduleRule(Targeted, Content, TimeStampedModel):
    """"Stage screens 18:00-20:00 -> Concert playlist": recurring or day-specific slots with a date range."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="schedule_rules")
    name = models.CharField(_("name"), max_length=200)
    enabled = models.BooleanField(_("enabled"), default=True)
    priority = models.PositiveSmallIntegerField(
        _("priority"), default=0, help_text=_("0-99. When schedules overlap, the higher number wins."))
    start_date = models.DateField(_("first day"), null=True, blank=True)
    end_date = models.DateField(_("last day"), null=True, blank=True)
    weekdays = models.JSONField(_("weekdays"), default=list, blank=True,
                                help_text=_("Empty: every day. 0 = Monday … 6 = Sunday."))
    start_time = models.TimeField(_("from"), null=True, blank=True, help_text=_("Empty: from midnight."))
    end_time = models.TimeField(_("until"), null=True, blank=True,
                                help_text=_("Empty: until midnight. Earlier than the start runs past midnight."))
    updated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["-priority", "name"]

    def __str__(self):
        return self.name

    def clean(self):
        if bool(self.layout_id) == bool(self.playlist_id):
            raise ValidationError(_("Choose either a layout or a playlist."))
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("Must not be before the first day.")})
        if self.start_time and self.end_time and self.start_time == self.end_time:
            raise ValidationError({"end_time": _("Start and end are the same.")})

    @property
    def effective_priority(self) -> int:
        return PRIORITY_SCHEDULE + min(self.priority, 99)


class OverrideQuerySet(models.QuerySet):
    def current(self, now=None):
        """Not cancelled and not expired (may start later)."""
        now = now or timezone.now()
        return self.filter(cancelled_at__isnull=True).filter(models.Q(expires_at__isnull=True)
                                                            | models.Q(expires_at__gt=now))

    def active(self, now=None):
        now = now or timezone.now()
        return self.current(now).filter(starts_at__lte=now)


class Override(Targeted, Content):
    """Push a layout, playlist or message to screens right now, with a priority level and an expiry."""

    class Level(models.TextChoices):
        URGENT = "urgent", _("Urgent (above schedules)")
        OVERRIDE = "override", _("Live override")
        EMERGENCY = "emergency", _("Emergency (above everything except evacuation)")

    PRIORITY = {"urgent": 200, "override": 300, "emergency": 400}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="overrides")
    title = models.CharField(_("title"), max_length=200)
    level = models.CharField(_("level"), max_length=10, choices=Level.choices, default=Level.OVERRIDE)
    message = models.TextField(_("message"), blank=True,
                               help_text=_("Shown in large letters when no layout or playlist is chosen."))
    starts_at = models.DateTimeField(_("starts"), default=timezone.now)
    expires_at = models.DateTimeField(_("ends"), null=True, blank=True, help_text=_("Empty: until cancelled."))
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    objects = OverrideQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def priority(self) -> int:
        return self.PRIORITY.get(self.level, 300)

    @property
    def is_message(self) -> bool:
        return not (self.layout_id or self.playlist_id)

    def content_label(self) -> str:
        return super().content_label() or str(_("Message"))

    def state(self, now=None) -> str:
        now = now or timezone.now()
        if self.cancelled_at:
            return "cancelled"
        if self.expires_at and self.expires_at <= now:
            return "expired"
        if self.starts_at > now:
            return "scheduled"
        return "active"
