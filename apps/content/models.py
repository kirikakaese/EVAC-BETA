# SPDX-License-Identifier: AGPL-3.0-or-later
"""Design system of the screens: themes (design tokens), fonts and the asset library.

Every object belongs to an event, or to the instance-wide **shared library** (``event`` is NULL, managed by
instance admins, usable by every event). Files are content addressed: ``content/<sha[:2]>/<sha>/<variant>``
under ``MEDIA_ROOT``, so identical uploads are stored once per owner and can be cached forever.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q
from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

from . import tokens as tok


def owner_q(event) -> Q:
    """Objects an event can use: its own plus the shared library."""
    return Q(event=event) | Q(event__isnull=True)


class Theme(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="themes")
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children",
                               help_text=_("Tokens not set here are inherited from this theme."))
    tokens = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1, editable=False)
    updated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["event", "key"], name="content_theme_unique_key"),
            models.UniqueConstraint(fields=["key"], condition=Q(event__isnull=True),
                                    name="content_theme_unique_shared_key"),
        ]

    def __str__(self):
        return self.name

    def chain(self) -> list[Theme]:
        """Ancestors first, this theme last (cycles are cut)."""
        seen, out, node = set(), [], self
        while node is not None and node.pk not in seen:
            seen.add(node.pk)
            out.append(node)
            node = node.parent
        return list(reversed(out))

    def layers(self) -> list[tuple[str, dict]]:
        return [(str(t.pk), dict(t.tokens or {})) for t in self.chain()]

    def resolved(self) -> dict:
        values = {k: p.get("default") for k, p in tok.schema()["properties"].items()}
        for _key, layer in self.layers():
            values.update(layer)
        return values


class FontFamily(TimeStampedModel):
    class Category(models.TextChoices):
        SANS = "sans", _("Sans serif")
        SERIF = "serif", _("Serif")
        MONO = "mono", _("Monospace")
        DISPLAY = "display", _("Display")

    FALLBACK = {"sans": 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
                "serif": 'Georgia, "Times New Roman", serif', "mono": 'ui-monospace, "DejaVu Sans Mono", monospace',
                "display": "system-ui, sans-serif"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="font_families")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.SANS)
    fallback = models.CharField(_("fallback fonts"), max_length=300, blank=True,
                                help_text=_("CSS font stack used while the font loads or for missing glyphs."))
    licence = models.TextField(_("licence note"), blank=True,
                               help_text=_("Where the font comes from and under which licence it may be used."))
    builtin = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "font families"

    def __str__(self):
        return self.name

    @property
    def css_family(self) -> str:
        """Unique family name used in @font-face (avoids clashes between events)."""
        return f"evac-{self.pk.hex}"

    @property
    def stack(self) -> str:
        return f'"{self.css_family}", {self.fallback or self.FALLBACK.get(self.category, self.FALLBACK["sans"])}'


class FontFile(models.Model):
    class Style(models.TextChoices):
        NORMAL = "normal", _("normal")
        ITALIC = "italic", _("italic")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(FontFamily, on_delete=models.CASCADE, related_name="files")
    #: uploaded fonts are stored as content/<sha[:2]>/<sha>/font.woff2 (see storage.py)
    sha256 = models.CharField(max_length=64, db_index=True, blank=True)
    static_path = models.CharField(max_length=200, blank=True, help_text="built-in fonts ship as static files")
    original_name = models.CharField(max_length=200, blank=True)
    original_format = models.CharField(max_length=8, blank=True)
    weight_min = models.PositiveSmallIntegerField(default=400)
    weight_max = models.PositiveSmallIntegerField(default=400)
    style = models.CharField(max_length=8, choices=Style.choices, default=Style.NORMAL)
    axes = models.JSONField(default=list, blank=True)
    unicode_range = models.CharField(max_length=500, blank=True)
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["family__name", "style", "weight_min"]

    def __str__(self):
        return f"{self.family} {self.weight_label} {self.style}"

    @property
    def weight_label(self) -> str:
        return str(self.weight_min) if self.weight_min == self.weight_max else f"{self.weight_min}–{self.weight_max}"

    @property
    def is_variable(self) -> bool:
        return bool(self.axes)

    def static_url(self) -> str:
        return static(self.static_path) if self.static_path else ""


class AssetFolder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="asset_folders")
    name = models.CharField(max_length=120)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.parent} / {self.name}" if self.parent_id else self.name


class Asset(TimeStampedModel):
    class Kind(models.TextChoices):
        IMAGE = "image", _("image")
        SVG = "svg", _("SVG")
        VIDEO = "video", _("video")
        AUDIO = "audio", _("audio")
        PDF = "pdf", _("PDF")
        LOTTIE = "lottie", _("Lottie animation")

    class Status(models.TextChoices):
        PROCESSING = "processing", _("processing")
        READY = "ready", _("ready")
        FAILED = "failed", _("failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="assets")
    folder = models.ForeignKey(AssetFolder, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    name = models.CharField(max_length=200)
    alt_text = models.CharField(_("alternative text"), max_length=300, blank=True,
                                help_text=_("Describes the content for people who cannot see it."))
    credit = models.CharField(_("credit / licence"), max_length=300, blank=True)
    tags = models.JSONField(default=list, blank=True)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    mime = models.CharField(max_length=100)
    sha256 = models.CharField(max_length=64, db_index=True)
    original_name = models.CharField(max_length=255)
    extension = models.CharField(max_length=10)
    size = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration = models.FloatField(null=True, blank=True)
    #: variant name -> {"file": "<file name>", "mime": ..., "size": ...}; "original" is always present
    variants = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROCESSING)
    note = models.CharField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "sha256"], name="content_asset_unique_per_owner")]

    def __str__(self):
        return self.name

    def variant(self, *names: str) -> str | None:
        """First existing variant of ``names`` (e.g. ``variant("thumb", "original")``)."""
        return next((n for n in names if n in (self.variants or {})), None)

    @property
    def is_shared(self) -> bool:
        return self.event_id is None
