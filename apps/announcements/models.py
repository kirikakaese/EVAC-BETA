# SPDX-License-Identifier: AGPL-3.0-or-later
"""Announcements (brief §6, ADR-0019): priority levels, templates, approval, scheduling, targeting and delivery.

An announcement is written once and delivered through channels: screens (banner, ticker, card or full-screen
takeover, depending on its level), the public feed, webhooks, staff notifications and - with Phase 2 part 2 -
e-mail, ntfy, Matrix, Telegram, Mastodon and Web Push. Every delivery attempt is a :class:`Delivery` row, so the
delivery report shows per channel what happened.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Level(models.Model):
    """A priority level (configurable per event; built-in defaults info, important, urgent, emergency)."""

    class Display(models.TextChoices):
        BANNER = "banner", _("Banner along the bottom")
        TICKER = "ticker", _("Scrolling ticker")
        CARD = "card", _("Card over the content")
        TAKEOVER = "takeover", _("Full screen")

    class Sound(models.TextChoices):
        NONE = "none", _("No sound")
        CHIME = "chime", _("Chime")
        GONG = "gong", _("Gong")
        ALERT = "alert", _("Alert tone")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="announcement_levels")
    key = models.SlugField(max_length=40)
    name = models.CharField(_("name"), max_length=80)
    rank = models.PositiveSmallIntegerField(_("rank"), default=10,
                                            help_text=_("Higher ranks win when several announcements show."))
    colour = models.CharField(_("colour"), max_length=7, default="#2563eb")
    display = models.CharField(_("on screens"), max_length=10, choices=Display.choices, default=Display.BANNER)
    sound = models.CharField(_("sound"), max_length=10, choices=Sound.choices, default=Sound.NONE)
    min_display_seconds = models.PositiveIntegerField(_("show for at least (seconds)"), default=30)
    repeat_every_minutes = models.PositiveIntegerField(
        _("repeat every (minutes)"), default=0, help_text=_("0: show once. Otherwise again until it ends."))
    default_channels = models.JSONField(_("default channels"), default=list, blank=True)
    requires_approval = models.BooleanField(_("always needs approval"), default=False)
    speak = models.BooleanField(_("read aloud on screens"), default=False,
                                help_text=_("Screens with sound speak the announcement (offline speech, when a voice "
                                            "is installed)."))
    emergency = models.BooleanField(
        _("emergency level"), default=False,
        help_text=_("Needs the emergency permission (two-factor session), skips approval and takes over screens "
                    "above live overrides."))

    class Meta:
        ordering = ["-rank", "name"]
        constraints = [models.UniqueConstraint(fields=["event", "key"], name="announcements_level_unique_key")]

    def __str__(self):
        return self.name

    @property
    def screen_priority(self) -> int:
        """Band in the screen program (evacuation 1000 > emergency 500 > overrides 200-400 > urgent 250 ...)."""
        if self.emergency:
            return 500
        return 250 if self.display == self.Display.TAKEOVER else 0


class Template(TimeStampedModel):
    """Reusable text with ``{{variables}}`` ("Lost child: {{description}} - please contact {{desk}}")."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="announcement_templates")
    name = models.CharField(_("name"), max_length=120)
    level = models.ForeignKey(Level, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                              verbose_name=_("level"))
    title = models.CharField(_("title"), max_length=200)
    body = models.TextField(_("text"), blank=True)
    short = models.CharField(_("short text (SMS, ticker)"), max_length=160, blank=True)
    layout = models.ForeignKey("content.Layout", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                               verbose_name=_("layout for full-screen display"),
                               help_text=_("Its texts may use {{ announcement.title }} and {{ announcement.text }}."))
    builtin = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Announcement(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PENDING = "pending", _("Waiting for approval")
        SCHEDULED = "scheduled", _("Scheduled")
        LIVE = "live", _("Published")
        REJECTED = "rejected", _("Rejected")
        CANCELLED = "cancelled", _("Cancelled")
        ENDED = "ended", _("Ended")

    class Recurrence(models.TextChoices):
        NONE = "", _("Once")
        DAILY = "daily", _("Every day")
        WEEKLY = "weekly", _("Every week")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="announcements")
    level = models.ForeignKey(Level, on_delete=models.PROTECT, related_name="announcements", verbose_name=_("level"))
    template = models.ForeignKey(Template, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    variables = models.JSONField(default=dict, blank=True)
    title = models.CharField(_("title"), max_length=200)
    body = models.TextField(_("text"), blank=True)
    short = models.CharField(_("short text (SMS, ticker)"), max_length=160, blank=True,
                             help_text=_("Empty: the title."))
    # targeting
    all_screens = models.BooleanField(_("everywhere"), default=True)
    venues = models.ManyToManyField("venues.Venue", blank=True, related_name="+", verbose_name=_("venues"))
    zones = models.ManyToManyField("venues.Zone", blank=True, related_name="+", verbose_name=_("zones"))
    rooms = models.ManyToManyField("venues.Room", blank=True, related_name="+", verbose_name=_("rooms"))
    screen_groups = models.ManyToManyField("screens.ScreenGroup", blank=True, related_name="+",
                                           verbose_name=_("screen groups"))
    screens = models.ManyToManyField("screens.Screen", blank=True, related_name="+", verbose_name=_("screens"))
    channels = models.JSONField(_("channels"), default=list, blank=True)
    #: optional text per channel key (shorter for social media, ...); empty: the default text
    channel_texts = models.JSONField(default=dict, blank=True)
    # timing
    #: limits channels that reach people (staff app, notifications) to these groups: ["roles:<id>", ...] (ADR-0025)
    audiences = models.JSONField(_("audiences"), default=list, blank=True)
    #: relative scheduling: "<anchor source>:<id>"; starts_at follows the anchor while not yet sent (ADR-0025)
    anchor = models.CharField(_("relative to"), max_length=200, blank=True)
    anchor_edge = models.CharField(max_length=5, choices=[("start", _("start")), ("end", _("end"))], default="start")
    anchor_offset = models.IntegerField(default=0, help_text="minutes; negative = before")
    anchor_label = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField(_("send at"), default=timezone.now)
    ends_at = models.DateTimeField(_("show until"), null=True, blank=True,
                                   help_text=_("Empty: the level's display time (or until cancelled when "
                                               "it repeats)."))
    recurrence = models.CharField(_("repeat"), max_length=10, choices=Recurrence.choices, blank=True, default="")
    recurrence_until = models.DateField(_("repeat until"), null=True, blank=True)
    # workflow
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    last_occurrence = models.DateTimeField(null=True, blank=True)
    # speech (ADR-0022): rendered once by Piper, stored as tts/<key>.<ext>
    class Speech(models.TextChoices):
        NONE = "", _("Not spoken")
        PENDING = "pending", _("Being prepared")
        READY = "ready", _("Ready")
        FAILED = "failed", _("Failed")
        UNAVAILABLE = "unavailable", _("No voice installed")

    speech_status = models.CharField(max_length=12, choices=Speech.choices, blank=True, default="")
    speech_file = models.CharField(max_length=80, blank=True)  # "<key>.<ext>"
    speech_detail = models.CharField(max_length=300, blank=True)
    #: the spoken file is a recording (e.g. announced by phone through DIAL), not rendered from the text
    speech_recorded = models.BooleanField(default=False)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return self.title

    @property
    def text(self) -> str:
        return self.body or self.title

    @property
    def short_text(self) -> str:
        return self.short or self.title[:160]

    def target_label(self) -> str:
        if self.all_screens:
            return str(_("Everywhere"))
        parts = [*self.venues.all(), *self.zones.all(), *self.rooms.all(), *self.screen_groups.all(),
                 *self.screens.all()]
        return ", ".join(str(p) for p in parts) or str(_("Nowhere"))


class Delivery(models.Model):
    """One channel delivery of one occurrence (the delivery report)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SENT = "sent", _("Delivered")
        FAILED = "failed", _("Failed")
        SKIPPED = "skipped", _("Skipped")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField(max_length=40)
    occurrence = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    recipients = models.PositiveIntegerField(default=0)
    detail = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["announcement", "channel", "occurrence"],
                                               name="announcements_delivery_unique")]

    def __str__(self):
        return f"{self.announcement} → {self.channel}"
