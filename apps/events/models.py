# SPDX-License-Identifier: AGPL-3.0-or-later
"""Events (the tenant root), lifecycle, memberships, roles, scoped role assignments, invitations."""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid
import zoneinfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

color_validator = RegexValidator(r"^#[0-9a-fA-F]{6}$", _("Use a hex colour like #1d4ed8."))
RESERVED_SLUGS = {"admin", "api", "setup", "static", "media", "docs", "accounts", "settings", "new", "invite",
                  "player", "ws", "sse", "poll"}


def validate_timezone(value: str) -> None:
    if value not in zoneinfo.available_timezones():
        raise ValidationError(_("Unknown time zone %(tz)s."), params={"tz": value})


def validate_slug(value: str) -> None:
    if value in RESERVED_SLUGS:
        raise ValidationError(_("This short name is reserved."))


class EventQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not getattr(user, "is_authenticated", False):
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(memberships__user=user).distinct()


class Event(TimeStampedModel):
    class State(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SETUP = "setup", _("Setup")
        LIVE = "live", _("Live")
        TEARDOWN = "teardown", _("Teardown")
        ARCHIVED = "archived", _("Archived")

    #: allowed lifecycle moves (forward through the lifecycle, one step back to correct mistakes)
    TRANSITIONS: dict[str, tuple[str, ...]] = {
        "draft": ("setup",),
        "setup": ("draft", "live"),
        "live": ("setup", "teardown"),
        "teardown": ("live", "archived"),
        "archived": ("teardown",),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(_("short name"), max_length=50, unique=True, validators=[validate_slug],
                            help_text=_("Used in URLs: /e/<short name>/"))
    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    state = models.CharField(max_length=10, choices=State.choices, default=State.DRAFT, db_index=True)
    timezone = models.CharField(_("time zone"), max_length=64, default="UTC", validators=[validate_timezone])
    start_date = models.DateField(_("first day"), null=True, blank=True)
    end_date = models.DateField(_("last day"), null=True, blank=True)
    venues = models.ManyToManyField("venues.Venue", blank=True, related_name="events")
    # branding
    logo = models.ImageField(upload_to="events/logos/", null=True, blank=True)
    primary_color = models.CharField(_("primary colour"), max_length=7, default="#2563eb",
                                     validators=[color_validator])
    accent_color = models.CharField(_("accent colour"), max_length=7, default="#22d3ee", validators=[color_validator])
    default_theme = models.CharField(_("default theme"), max_length=64, blank=True,
                                     help_text=_("Theme key used by screens (Phase 1 designer)."))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["-start_date", "name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("The last day must not be before the first day.")})

    @property
    def tz(self) -> zoneinfo.ZoneInfo:
        return zoneinfo.ZoneInfo(self.timezone)

    @property
    def is_archived(self) -> bool:
        return self.state == self.State.ARCHIVED

    def can_transition(self, target: str) -> bool:
        return target in self.TRANSITIONS.get(self.state, ())

    def transition(self, target: str, *, user=None, request=None, reason: str = "") -> None:
        from apps.core.audit import log
        from apps.core.webhooks import emit

        if not self.can_transition(target):
            raise ValidationError(_("An event cannot go from %(a)s to %(b)s.") % {"a": self.state, "b": target})
        before = self.state
        self.state = target
        self.save(update_fields=["state", "updated_at"])
        log(action="event.state_changed", actor=user, target=self, event=self, request=request,
            message=reason or f"{before} -> {target}", changes={"state": [before, target]})
        emit("event.state_changed", {"slug": self.slug, "from": before, "to": target}, event=self)


class ScheduledTransition(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="scheduled_transitions")
    target_state = models.CharField(max_length=10, choices=Event.State.choices)
    at = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    applied_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["at"]

    def __str__(self):
        return f"{self.event} -> {self.target_state} at {self.at:%Y-%m-%d %H:%M}"


class Role(models.Model):
    """A named set of permission patterns within one event (built-in or custom).

    ``permissions`` holds glob patterns over registered permission keys (``screens.*``, ``*.view``,
    ``!events.delete``). ``require_2fa``: the role's permissions only apply in a two-factor verified session.
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="roles")
    key = models.SlugField(max_length=50)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    require_2fa = models.BooleanField(_("require two-factor authentication"), default=False)
    builtin = models.BooleanField(default=False, editable=False)
    order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["order", "name"]
        constraints = [models.UniqueConstraint(fields=["event", "key"], name="uniq_role_key")]

    def __str__(self):
        return self.name

    def expanded(self) -> set[str]:
        from apps.core.registry import registry

        return registry.expand(self.permissions)

    @property
    def grants_sensitive(self) -> bool:
        from apps.core.registry import registry

        return bool(self.expanded() & registry.sensitive_permissions())


class Membership(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    created_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")

    class Meta:
        ordering = ["user__email"]
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="uniq_membership")]

    def __str__(self):
        return f"{self.user} @ {self.event}"


class RoleAssignment(models.Model):
    """A role granted to a member, optionally restricted to one scope object (venue, zone, team, ...)."""

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="assignments")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="assignments")
    scope_kind = models.CharField(max_length=32, blank=True)
    scope_id = models.CharField(max_length=64, blank=True)
    scope_label = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "role", "scope_kind", "scope_id"],
                                               name="uniq_role_assignment")]

    def __str__(self):
        scope = f" ({self.scope_kind}: {self.scope_label or self.scope_id})" if self.scope_kind else ""
        return f"{self.role}{scope}"


class Invitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="invitations")
    scope_kind = models.CharField(max_length=32, blank=True)
    scope_id = models.CharField(max_length=64, blank=True)
    scope_label = models.CharField(max_length=200, blank=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} -> {self.event} ({self.role})"

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(cls, *, event, email, role, created_by=None, scope_kind="", scope_id="", scope_label=""):
        raw = secrets.token_urlsafe(32)
        ttl = getattr(settings, "EVAC_INVITATION_TTL_HOURS", 168)
        inv = cls.objects.create(event=event, email=email.strip().lower(), role=role, created_by=created_by,
                                 scope_kind=scope_kind, scope_id=scope_id, scope_label=scope_label,
                                 token_hash=cls.hash_token(raw), expires_at=timezone.now() + dt.timedelta(hours=ttl))
        return inv, raw

    @property
    def is_valid(self) -> bool:
        return self.accepted_at is None and self.expires_at > timezone.now()
