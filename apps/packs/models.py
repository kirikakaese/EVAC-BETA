# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pack signing keys, trusted keys and staged imports (ADR-0024)."""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class SigningKey(models.Model):
    """The instance's Ed25519 key that signs exported packs (one row, created on first export; private key
    encrypted with ``apps.core.crypto``)."""

    private_key_encrypted = models.TextField()
    public_key = models.CharField(max_length=64)  # base64 of the 32 raw bytes
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pack signing key {self.public_key[:12]}…"


class TrustedKey(models.Model):
    """A public key whose packs this instance trusts (packs signed with it import without a warning)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    public_key = models.CharField(max_length=64, unique=True)
    name = models.CharField(_("name"), max_length=200)
    added_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PackImport(models.Model):
    """An uploaded, downloaded or gallery pack waiting for review, and what its import did."""

    class Source(models.TextChoices):
        UPLOAD = "upload", _("Upload")
        URL = "url", _("URL")
        GALLERY = "gallery", _("Gallery")

    class Status(models.TextChoices):
        FETCHING = "fetching", _("Downloading")
        READY = "ready", _("Ready to import")
        FAILED = "failed", _("Failed")
        IMPORTED = "imported", _("Imported")

    class Trust(models.TextChoices):
        BUILTIN = "builtin", _("Built in")
        TRUSTED = "trusted", _("Signed by a trusted key")
        UNTRUSTED = "untrusted", _("Signed by an unknown key")
        UNSIGNED = "unsigned", _("Not signed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="pack_imports")
    source = models.CharField(max_length=8, choices=Source.choices)
    url = models.URLField(max_length=1000, blank=True)
    gallery_key = models.CharField(max_length=64, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.FETCHING)
    error = models.TextField(blank=True)
    name = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    #: section key -> [{"id", "name"}] (what the pack contains, for the review page)
    contents = models.JSONField(default=dict, blank=True)
    trust = models.CharField(max_length=10, choices=Trust.choices, blank=True)
    signer = models.CharField(max_length=200, blank=True)
    public_key = models.CharField(max_length=64, blank=True)
    result = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    imported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or self.file_name or str(self.pk)
