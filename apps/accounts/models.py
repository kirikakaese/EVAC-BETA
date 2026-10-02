# SPDX-License-Identifier: AGPL-3.0-or-later
"""User accounts, service tokens and second factors.

Users have one account across all events. Per-event roles live in ``events.Membership`` /
``events.RoleAssignment``; instance admins are superusers.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core import crypto


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("email_verified", True)
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("e-mail address"), unique=True)
    display_name = models.CharField(_("display name"), max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    oidc_subject = models.CharField(max_length=255, blank=True, db_index=True)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.display_name or self.email.split("@", 1)[0]

    def get_short_name(self):
        return str(self)

    def get_full_name(self):
        return self.display_name or self.email

    @property
    def has_two_factor(self) -> bool:
        return self.totp_devices.filter(confirmed=True).exists() or self.webauthn_credentials.exists()


class ServiceToken(models.Model):
    """Bearer token for integrations and the CLI (``Authorization: Bearer evac_...``).

    Only the SHA-256 of the token is stored. Scopes are ``<module>:read`` / ``<module>:write`` (write
    implies read), ``<module>:*`` or ``*``. A token never has more rights than its owner; ``event``
    restricts it to one event.
    """

    PREFIX = "evac_"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="service_tokens")
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="service_tokens",
                              help_text=_("Restrict the token to one event; empty = all events of the owner."))
    scopes = models.JSONField(default=list, blank=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    token_prefix = models.CharField(max_length=16, editable=False)
    is_active = models.BooleanField(default=True)
    created_with_2fa = models.BooleanField(
        default=False, editable=False,
        help_text=_("Minted in a two-factor verified session; only such tokens can use sensitive permissions."))
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.token_prefix}…)"

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(cls, *, name, owner, event=None, scopes=None, expires_at=None, created_with_2fa=False):
        """Create a token and return ``(token, raw)``. The raw token is only available now."""
        raw = cls.PREFIX + secrets.token_urlsafe(32)
        tok = cls.objects.create(name=name, owner=owner, event=event, scopes=list(scopes or []),
                                 expires_at=expires_at, token_hash=cls.hash_token(raw), token_prefix=raw[:12],
                                 created_with_2fa=created_with_2fa)
        return tok, raw

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def has_scope(self, scope: str) -> bool:
        """``scope`` is ``<module>:read`` or ``<module>:write``."""
        if not self.scopes or "*" in self.scopes:
            return True
        module, _, mode = scope.partition(":")
        if scope in self.scopes or f"{module}:*" in self.scopes:
            return True
        return mode == "read" and f"{module}:write" in self.scopes


class TOTPDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="totp_devices")
    name = models.CharField(max_length=60, default="Authenticator app")
    secret_encrypted = models.TextField()
    confirmed = models.BooleanField(default=False)
    last_counter = models.BigIntegerField(default=-1, help_text=_("Last accepted time step (replay protection)."))
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def secret(self) -> str:
        return crypto.decrypt(self.secret_encrypted)

    @secret.setter
    def secret(self, value: str) -> None:
        self.secret_encrypted = crypto.encrypt(value)


class WebAuthnCredential(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="webauthn_credentials")
    name = models.CharField(max_length=60, default="Security key")
    credential_id = models.CharField(max_length=512, unique=True)
    public_key = models.TextField()
    sign_count = models.BigIntegerField(default=0)
    transports = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class RecoveryCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def hash_code(code: str) -> str:
        return hashlib.sha256(code.replace("-", "").strip().lower().encode()).hexdigest()
