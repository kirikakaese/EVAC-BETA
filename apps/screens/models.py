# SPDX-License-Identifier: AGPL-3.0-or-later
"""Screens (players), screen groups and pairing requests.

A screen belongs to one event (the tenant root, so RBAC and audit work as everywhere else) and may be
placed in a venue, zone and room. It authenticates with a per-screen device token (``evacscreen_…``,
stored as a SHA-256 hash, revocable). A screen row can exist before a device is paired (pre-provisioned)
and can be re-paired to new hardware.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

TOKEN_PREFIX = "evacscreen_"
#: Pairing codes avoid look-alike characters (0/O, 1/I/L) so they can be typed from across a hall.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def normalize_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch in CODE_ALPHABET)


class ScreenGroup(TimeStampedModel):
    """Manual groups list their screens; dynamic groups also include every screen that matches a rule."""

    class Kind(models.TextChoices):
        MANUAL = "manual", _("Manual")
        DYNAMIC = "dynamic", _("Dynamic")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="screen_groups")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MANUAL)
    match_tags = models.JSONField(_("tags"), default=list, blank=True,
                                  help_text=_("Dynamic: screens with any of these tags."))
    match_venues = models.ManyToManyField("venues.Venue", blank=True, related_name="+", verbose_name=_("venues"))
    match_zones = models.ManyToManyField("venues.Zone", blank=True, related_name="+", verbose_name=_("zones"))
    match_rooms = models.ManyToManyField("venues.Room", blank=True, related_name="+", verbose_name=_("rooms"))

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="screens_group_unique_name")]

    def __str__(self):
        return self.name

    def evac_scope_chain(self):
        return [("screen_group", str(self.pk))]

    def matches(self, screen: Screen) -> bool:
        if self.kind != self.Kind.DYNAMIC:
            return False
        if set(self.match_tags or []) & set(screen.tags or []):
            return True
        return bool(
            (screen.venue_id and self.match_venues.filter(pk=screen.venue_id).exists())
            or (screen.zone_id and self.match_zones.filter(pk=screen.zone_id).exists())
            or (screen.room_id and self.match_rooms.filter(pk=screen.room_id).exists())
        )

    def screens(self) -> models.QuerySet[Screen]:
        """Manual members plus, for dynamic groups, every screen of the event that matches the rule."""
        base = Screen.objects.filter(event_id=self.event_id)
        q = models.Q(manual_groups=self)
        if self.kind == self.Kind.DYNAMIC:
            q |= (models.Q(venue__in=self.match_venues.all()) | models.Q(zone__in=self.match_zones.all())
                  | models.Q(room__in=self.match_rooms.all()))
            tags = set(self.match_tags or [])
            if tags:  # JSON containment is not portable across databases; events have few screens
                q |= models.Q(pk__in=[pk for pk, t in base.values_list("pk", "tags") if tags & set(t or [])])
        return base.filter(q).distinct()


class ScreenQuerySet(models.QuerySet):
    def paired(self):
        return self.filter(token_hash__isnull=False, revoked_at__isnull=True)


class Screen(TimeStampedModel):
    class Health(models.TextChoices):
        UNPAIRED = "unpaired", _("not paired")
        ONLINE = "online", _("online")
        STALE = "stale", _("stale")
        OFFLINE = "offline", _("offline")
        REVOKED = "revoked", _("revoked")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="screens")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    venue = models.ForeignKey("venues.Venue", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    zone = models.ForeignKey("venues.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    room = models.ForeignKey("venues.Room", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    manual_groups = models.ManyToManyField(ScreenGroup, blank=True, related_name="manual_screens",
                                           verbose_name=_("groups"))
    #: place on the venue map (map editor, ADR-0027): floor (empty: outdoors), metres on that floor's plan and
    #: the direction the screen faces (degrees clockwise from the plan's "up"), used for evacuation arrows
    floor = models.ForeignKey("venues.Floor", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    position_x = models.FloatField(null=True, blank=True)
    position_y = models.FloatField(null=True, blank=True)
    facing = models.FloatField(null=True, blank=True)

    token_hash = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)
    token_prefix = models.CharField(max_length=24, blank=True, editable=False)
    paired_at = models.DateTimeField(null=True, blank=True)
    paired_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    revoked_at = models.DateTimeField(null=True, blank=True)

    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    #: what the player reported in its last heartbeat (version, resolution, orientation, uptime, slide, ...)
    reported = models.JSONField(default=dict, blank=True)
    #: last health state the offline sweep saw (to alert on transitions only)
    health_state = models.CharField(max_length=10, choices=Health.choices, default=Health.UNPAIRED)
    #: remote management: the last screenshot (``MEDIA_ROOT/screens/<id>/screenshot.jpg``) and log lines
    screenshot_at = models.DateTimeField(null=True, blank=True)
    screenshot_error = models.CharField(max_length=300, blank=True)
    logs = models.JSONField(default=list, blank=True)
    logs_at = models.DateTimeField(null=True, blank=True)

    objects = ScreenQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_paired(self) -> bool:
        return bool(self.token_hash) and self.revoked_at is None

    def groups(self) -> list[ScreenGroup]:
        manual = set(self.manual_groups.values_list("pk", flat=True)) if not self._state.adding else set()
        return [g for g in ScreenGroup.objects.filter(event_id=self.event_id).prefetch_related(
            "match_venues", "match_zones", "match_rooms") if g.pk in manual or g.matches(self)]

    def evac_scope_chain(self):
        chain = []
        if self.venue_id:
            chain.append(("venue", str(self.venue_id)))
        if self.zone_id:
            chain.append(("zone", str(self.zone_id)))
        if self.room_id:
            chain.append(("room", str(self.room_id)))
        chain += [("screen_group", str(g.pk)) for g in self.groups()]
        return chain

    def issue_token(self) -> str:
        """Give the screen a new device token (invalidates the previous one) and return the raw value."""
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        self.token_hash = hash_secret(raw)
        self.token_prefix = raw[:len(TOKEN_PREFIX) + 6]
        self.revoked_at = None
        return raw

    def health(self, *, heartbeat_seconds: int = 10, offline_after: int = 60, now=None) -> str:
        if self.revoked_at is not None:
            return self.Health.REVOKED
        if not self.token_hash:
            return self.Health.UNPAIRED
        if self.last_seen_at is None:
            return self.Health.OFFLINE
        age = ((now or timezone.now()) - self.last_seen_at).total_seconds()
        if age <= max(3 * heartbeat_seconds, 15):
            return self.Health.ONLINE
        if age <= offline_after:
            return self.Health.STALE
        return self.Health.OFFLINE


#: badge CSS class per health state (badges carry a glyph, status is never shown by colour alone)
HEALTH_BADGE = {"online": "badge-ok", "stale": "badge-warn", "offline": "badge-offline", "unpaired": "badge-muted",
                "revoked": "badge-err"}


class PairingRequest(models.Model):
    """A player asked to be paired: it shows ``code`` and polls with its secret until staff claim it."""

    TTL_MINUTES = 30

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=CODE_LENGTH, db_index=True)
    secret_hash = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    info = models.JSONField(default=dict, blank=True)
    screen = models.ForeignKey(Screen, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    claimed_at = models.DateTimeField(null=True, blank=True)
    #: the new device token, encrypted, until the player picked it up (then cleared)
    token_encrypted = models.TextField(blank=True, editable=False)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def display_code(self) -> str:
        return f"{self.code[:3]}-{self.code[3:]}"
