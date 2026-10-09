# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API: ``/api/v1/events/<slug>/themes/``, ``…/fonts/``, ``…/assets/`` (event items and shared library)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.core import modules

from . import files, services
from .models import Asset, AssetFolder, FontFamily, FontFile, Layout, Theme, owner_q

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


class _Mixin(EventScopedMixin):
    scope_module = "content"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "content.view", "HEAD": "content.view", "OPTIONS": "content.view",
                         "default": "content.edit"}

    def get_event(self):
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("content", event):
            raise NotFound("The content module is switched off for this event.")
        return event

    def _writable(self, obj):
        if obj.event_id is None and not self.request.user.is_superuser:
            raise PermissionDenied("Only instance admins change the shared library.")


class ThemeSerializer(serializers.ModelSerializer):
    resolved = serializers.SerializerMethodField()
    shared = serializers.SerializerMethodField()

    class Meta:
        model = Theme
        fields = ["id", "key", "name", "description", "parent", "tokens", "resolved", "version", "shared",
                  "updated_at"]
        read_only_fields = ["id", "resolved", "version", "shared", "updated_at"]

    def get_resolved(self, obj) -> dict:
        return obj.resolved()

    def get_shared(self, obj) -> bool:
        return obj.event_id is None


@EVENT_SLUG
class ThemeViewSet(_Mixin, viewsets.ModelViewSet):
    """Themes (design tokens). ``PATCH`` with ``version`` fails with 409-like 400 when it changed meanwhile."""

    serializer_class = ThemeSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Theme.objects.none()
        return Theme.objects.filter(owner_q(self.get_event()))

    def _save(self, theme, data):
        tokens = data.pop("tokens", None)
        for k, v in data.items():
            setattr(theme, k, v)
        if theme.parent_id and not Theme.objects.filter(owner_q(self.get_event()), pk=theme.parent_id).exists():
            raise serializers.ValidationError({"parent": "Unknown theme."})
        expected = self.request.data.get("version")
        try:
            return services.save_theme(theme, actor=self.request.user, request=self.request, tokens=tokens,
                                       schema=services.theme_schema(self.get_event()),
                                       expected_version=int(expected) if expected else None)
        except ValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages}) from exc

    def perform_create(self, serializer):
        data = dict(serializer.validated_data)
        if Theme.objects.filter(event=self.get_event(), key=data.get("key")).exists():
            raise serializers.ValidationError({"key": "This key is taken."})
        serializer.instance = self._save(Theme(event=self.get_event()), data)

    def perform_update(self, serializer):
        self._writable(serializer.instance)
        serializer.instance = self._save(serializer.instance, dict(serializer.validated_data))

    def perform_destroy(self, instance):
        self._writable(instance)
        try:
            services.delete_theme(instance, actor=self.request.user, request=self.request)
        except ValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages}) from exc


class FontFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = FontFile
        fields = ["id", "weight_min", "weight_max", "style", "axes", "unicode_range", "size", "original_name", "url"]

    def get_url(self, obj) -> str:
        return obj.static_url() or files.portal_url(obj.sha256, "font.woff2")


class FontFamilySerializer(serializers.ModelSerializer):
    files = FontFileSerializer(many=True, read_only=True)
    stack = serializers.CharField(read_only=True)
    upload = serializers.FileField(write_only=True, required=False)
    subset = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = FontFamily
        fields = ["id", "name", "category", "fallback", "licence", "builtin", "stack", "files", "upload", "subset"]
        read_only_fields = ["id", "builtin", "stack", "files"]
        extra_kwargs = {"name": {"required": False}}


@EVENT_SLUG
class FontViewSet(_Mixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                  mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Font families. ``POST`` multipart with ``upload`` (font file), optional ``name``, ``category``,
    ``licence``, ``subset``; uploading a family name that exists adds the file to it."""

    serializer_class = FontFamilySerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return FontFamily.objects.none()
        return FontFamily.objects.filter(owner_q(self.get_event())).prefetch_related("files")

    def perform_create(self, serializer):
        d = serializer.validated_data
        if not d.get("upload"):
            raise serializers.ValidationError({"upload": "A font file is required."})
        try:
            ff = services.upload_font(self.get_event(), d["upload"], actor=self.request.user, request=self.request,
                                      name=d.get("name", ""), category=d.get("category", "sans"),
                                      licence=d.get("licence", ""), subset=d.get("subset", False))
        except ValidationError as exc:
            raise serializers.ValidationError({"upload": exc.messages}) from exc
        serializer.instance = ff.family

    def perform_destroy(self, instance):
        self._writable(instance)
        try:
            services.delete_font_family(instance, actor=self.request.user, request=self.request)
        except ValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages}) from exc


class AssetSerializer(serializers.ModelSerializer):
    urls = serializers.SerializerMethodField()
    upload = serializers.FileField(write_only=True, required=False)
    folder = serializers.PrimaryKeyRelatedField(queryset=AssetFolder.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Asset
        fields = ["id", "name", "alt_text", "credit", "tags", "folder", "kind", "mime", "size", "width", "height",
                  "duration", "status", "note", "urls", "upload", "created_at"]
        read_only_fields = ["id", "kind", "mime", "size", "width", "height", "duration", "status", "note", "urls",
                            "created_at"]
        extra_kwargs = {"name": {"required": False}}

    def get_urls(self, obj) -> dict:
        return {k: files.portal_url(obj.sha256, v["file"]) for k, v in (obj.variants or {}).items()}


@EVENT_SLUG
class AssetViewSet(_Mixin, viewsets.ModelViewSet):
    """Asset library. ``POST`` multipart with ``upload`` creates an asset (identical files are reused, 200)."""

    serializer_class = AssetSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Asset.objects.none()
        qs = Asset.objects.filter(owner_q(self.get_event()))
        kind = self.request.query_params.get("kind")
        return qs.filter(kind=kind) if kind else qs

    def perform_create(self, serializer):
        d = serializer.validated_data
        if not d.get("upload"):
            raise serializers.ValidationError({"upload": "A file is required."})
        try:
            asset, _created = services.upload_asset(self.get_event(), d["upload"], actor=self.request.user,
                                                    request=self.request, folder=d.get("folder"),
                                                    tags=d.get("tags", []), name=d.get("name", ""))
        except ValidationError as exc:
            raise serializers.ValidationError({"upload": exc.messages}) from exc
        serializer.instance = asset

    def perform_update(self, serializer):
        asset = serializer.instance
        self._writable(asset)
        before = {f: getattr(asset, f) for f in ("name", "alt_text", "credit", "tags")}
        for k, v in serializer.validated_data.items():
            if k != "upload":
                setattr(asset, k, v)
        services.save_asset(asset, actor=self.request.user, request=self.request, before=before)

    def perform_destroy(self, instance):
        self._writable(instance)
        try:
            services.delete_asset(instance, actor=self.request.user, request=self.request)
        except ValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages}) from exc


class LayoutSerializer(serializers.ModelSerializer):
    published_version = serializers.SerializerMethodField()

    class Meta:
        model = Layout
        fields = ["id", "key", "name", "description", "theme", "data", "version", "published_version", "is_default",
                  "updated_at"]
        read_only_fields = ["id", "version", "published_version", "is_default", "updated_at"]
        extra_kwargs = {"data": {"required": False}, "key": {"required": False}}

    def get_published_version(self, obj) -> int | None:
        return obj.published.number if obj.published_id else None


class PublishSerializer(serializers.Serializer):
    at = serializers.DateTimeField(required=False, help_text="Schedule instead of publishing now.")


@EVENT_SLUG
class LayoutViewSet(_Mixin, viewsets.ModelViewSet):
    """Layouts (format: docs/LAYOUTS.md). ``PATCH`` with ``data`` saves a new version; send ``version`` to
    detect concurrent edits. ``POST …/publish/`` puts the current draft on the screens."""

    serializer_class = LayoutSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Layout.objects.none()
        return Layout.objects.filter(event=self.get_event()).select_related("published")

    def perform_create(self, serializer):
        from django.utils.text import slugify

        d = serializer.validated_data
        key = d.get("key") or slugify(d["name"])[:64] or "layout"
        if Layout.objects.filter(event=self.get_event(), key=key).exists():
            raise serializers.ValidationError({"key": "This key is taken."})
        try:
            serializer.instance = services.create_layout(self.get_event(), name=d["name"], key=key,
                                                         actor=self.request.user, request=self.request,
                                                         data=d.get("data"))
        except ValidationError as exc:
            raise serializers.ValidationError({"data": exc.messages}) from exc

    def perform_update(self, serializer):
        layout = serializer.instance
        d = dict(serializer.validated_data)
        data = d.pop("data", None)
        for k, v in d.items():
            setattr(layout, k, v)
        layout.save()
        if data is not None:
            expected = self.request.data.get("version")
            try:
                services.save_layout(layout, data, actor=self.request.user, request=self.request,
                                     expected_version=int(expected) if expected else None)
            except ValidationError as exc:
                raise serializers.ValidationError({"data": exc.messages}) from exc

    def perform_destroy(self, instance):
        services.delete_layout(instance, actor=self.request.user, request=self.request)

    @extend_schema(request=PublishSerializer, responses={200: dict})
    @action(detail=True, methods=["post"])
    def publish(self, request, event_slug=None, pk=None):
        from apps.events import rbac

        layout = self.get_object()
        if not rbac.has_perm(request.user, self.get_event(), "content.publish", request=request):
            raise PermissionDenied("Missing permission content.publish.")
        data = PublishSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = services.publish_layout(layout, actor=request.user, request=request, at=data.validated_data.get("at"))
        return Response({"version": v.number, "scheduled": v.publish_at})


ROUTES = [
    (r"events/(?P<event_slug>[^/.]+)/themes", ThemeViewSet, "event-theme"),
    (r"events/(?P<event_slug>[^/.]+)/fonts", FontViewSet, "event-font"),
    (r"events/(?P<event_slug>[^/.]+)/assets", AssetViewSet, "event-asset"),
    (r"events/(?P<event_slug>[^/.]+)/layouts", LayoutViewSet, "event-layout"),
]
