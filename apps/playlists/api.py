# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API: ``/api/v1/events/<slug>/playlists/``, ``…/schedules/``, ``…/overrides/``, ``…/now-playing/``."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.content.models import Layout
from apps.core import modules
from apps.screens.models import Screen, ScreenGroup

from . import services
from .models import Override, Playlist, PlaylistItem, ScheduleRule

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


class _Mixin(EventScopedMixin):
    scope_module = "playlists"
    module = "playlists"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "playlists.view", "HEAD": "playlists.view", "OPTIONS": "playlists.view",
                         "default": "playlists.edit"}

    def get_event(self):
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled(self.module, event):
            raise NotFound(f"The {self.module} module is switched off for this event.")
        return event

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["event"] = self.get_event()
        return ctx


class EventRelated(serializers.PrimaryKeyRelatedField):
    """A related object of the request's event."""

    def __init__(self, model, **kwargs):
        self.model = model
        super().__init__(**kwargs)

    def get_queryset(self):
        return self.model.objects.filter(event=self.context["event"])


class ItemSerializer(serializers.ModelSerializer):
    layout = EventRelated(Layout, required=False, allow_null=True)
    child = EventRelated(Playlist, required=False, allow_null=True)

    class Meta:
        model = PlaylistItem
        fields = ["id", "layout", "child", "duration", "weight", "tags", "condition", "valid_from", "valid_until",
                  "enabled"]
        read_only_fields = ["id"]


class PlaylistSerializer(serializers.ModelSerializer):
    items = ItemSerializer(many=True, required=False)

    class Meta:
        model = Playlist
        fields = ["id", "name", "description", "mode", "default_duration", "is_default", "items", "updated_at"]
        read_only_fields = ["id", "updated_at"]


@EVENT_SLUG
class PlaylistViewSet(_Mixin, viewsets.ModelViewSet):
    """Playlists. ``items`` (in order) replaces all items when sent; nested playlists use ``child``."""

    serializer_class = PlaylistSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Playlist.objects.none()
        return Playlist.objects.filter(event=self.get_event()).prefetch_related("items")

    def _save(self, serializer, instance=None):
        d = dict(serializer.validated_data)
        items = d.pop("items", None)
        pl = instance or Playlist(event=self.get_event())
        for k, v in d.items():
            setattr(pl, k, v)
        try:
            with transaction.atomic():
                services.save_playlist(pl, actor=self.request.user, request=self.request)
                if items is not None:
                    pl.items.all().delete()
                    for data in items:
                        services.save_item(PlaylistItem(playlist=pl, **data), actor=self.request.user,
                                           request=self.request)
        except ValidationError as exc:
            raise serializers.ValidationError({"items": exc.messages}) from exc
        serializer.instance = pl

    def perform_create(self, serializer):
        self._save(serializer)

    def perform_update(self, serializer):
        self._save(serializer, serializer.instance)

    def perform_destroy(self, instance):
        try:
            services.delete_playlist(instance, actor=self.request.user, request=self.request)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class TargetFields(serializers.Serializer):
    groups = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=ScreenGroup.objects.none())
    screens = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Screen.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        event = self.context.get("event")
        if event is not None and event.pk:
            self.fields["groups"].child_relation.queryset = ScreenGroup.objects.filter(event=event)
            self.fields["screens"].child_relation.queryset = Screen.objects.filter(event=event)


class ScheduleSerializer(TargetFields, serializers.ModelSerializer):
    layout = EventRelated(Layout, required=False, allow_null=True)
    playlist = EventRelated(Playlist, required=False, allow_null=True)

    class Meta:
        model = ScheduleRule
        fields = ["id", "name", "enabled", "priority", "playlist", "layout", "all_screens", "groups", "screens",
                  "weekdays", "start_time", "end_time", "start_date", "end_date", "updated_at"]
        read_only_fields = ["id", "updated_at"]

    def validate_weekdays(self, value):
        if not isinstance(value, list) or any(not isinstance(d, int) or not 0 <= d <= 6 for d in value):
            raise serializers.ValidationError("A list of numbers 0 (Monday) to 6 (Sunday).")
        return sorted(set(value))


@EVENT_SLUG
class ScheduleViewSet(_Mixin, viewsets.ModelViewSet):
    """Schedule rules: content (playlist or layout), screens and time slots (event time zone)."""

    module = "schedules"
    serializer_class = ScheduleSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ScheduleRule.objects.none()
        return ScheduleRule.objects.filter(event=self.get_event()).prefetch_related("groups", "screens")

    def _save(self, serializer, rule):
        d = dict(serializer.validated_data)
        m2m = {k: d.pop(k) for k in ("groups", "screens") if k in d}
        for k, v in d.items():
            setattr(rule, k, v)
        try:
            serializer.instance = services.save_rule(rule, actor=self.request.user, request=self.request, m2m=m2m)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def perform_create(self, serializer):
        self._save(serializer, ScheduleRule(event=self.get_event()))

    def perform_update(self, serializer):
        self._save(serializer, serializer.instance)

    def perform_destroy(self, instance):
        services.delete_rule(instance, actor=self.request.user, request=self.request)


class OverrideSerializer(TargetFields, serializers.ModelSerializer):
    layout = EventRelated(Layout, required=False, allow_null=True)
    playlist = EventRelated(Playlist, required=False, allow_null=True)
    state = serializers.SerializerMethodField()

    class Meta:
        model = Override
        fields = ["id", "title", "level", "message", "layout", "playlist", "all_screens", "groups", "screens",
                  "starts_at", "expires_at", "cancelled_at", "state", "created_at"]
        read_only_fields = ["id", "cancelled_at", "state", "created_at"]
        extra_kwargs = {"starts_at": {"required": False}}

    def get_state(self, obj) -> str:
        return obj.state()


@EVENT_SLUG
class OverrideViewSet(_Mixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      viewsets.GenericViewSet):
    """Live overrides. Create pushes at once (or at ``starts_at``); ``expires_at`` empty = until cancelled.
    ``POST …/cancel/`` ends it. Levels: ``urgent`` < ``override`` < ``emergency`` (needs
    ``playlists.emergency``, a sensitive permission)."""

    module = "overrides"
    serializer_class = OverrideSerializer
    event_permissions = {"GET": "playlists.view", "HEAD": "playlists.view", "OPTIONS": "playlists.view"}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Override.objects.none()
        qs = Override.objects.filter(event=self.get_event()).prefetch_related("groups", "screens")
        if self.request.query_params.get("current"):
            qs = qs.current()
        return qs

    def _check(self, level, all_screens, groups, screens):
        perm = "playlists.emergency" if level == Override.Level.EMERGENCY else "playlists.override"
        if not services.may_target(self.request.user, self.get_event(), perm, all_screens=all_screens,
                                   groups=groups, screens=screens, request=self.request):
            raise PermissionDenied(f"Missing permission {perm} for these screens.")

    def perform_create(self, serializer):
        d = dict(serializer.validated_data)
        m2m = {k: d.pop(k, []) for k in ("groups", "screens")}
        self._check(d.get("level", Override.Level.OVERRIDE), d.get("all_screens", False), m2m["groups"],
                    m2m["screens"])
        d.setdefault("starts_at", timezone.now())
        try:
            serializer.instance = services.push_override(Override(event=self.get_event(), **d),
                                                         actor=self.request.user, request=self.request, m2m=m2m)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    @extend_schema(request=None, responses={200: OverrideSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, event_slug=None, pk=None):
        ov = self.get_object()
        self._check(ov.level, ov.all_screens, list(ov.groups.all()), list(ov.screens.all()))
        services.cancel_override(ov, actor=request.user, request=request)
        return Response(self.get_serializer(ov).data)


class NowPlayingSerializer(serializers.Serializer):
    screen = serializers.UUIDField()
    name = serializers.CharField()
    source = serializers.CharField(allow_null=True)
    entry = serializers.CharField(allow_null=True)
    title = serializers.CharField(allow_null=True)
    layout = serializers.CharField(allow_null=True)
    until = serializers.DateTimeField(allow_null=True)


@EVENT_SLUG
class NowPlayingViewSet(_Mixin, viewsets.GenericViewSet):
    """What every paired screen shows right now (source: override, schedule or default)."""

    serializer_class = NowPlayingSerializer
    queryset = Screen.objects.none()

    @extend_schema(responses={200: NowPlayingSerializer(many=True)})
    def list(self, request, event_slug=None):
        import datetime as dt

        out = []
        for screen in Screen.objects.paired().filter(event=self.get_event()):
            found = services.now_playing(screen) or {}
            end = found.get("end")
            out.append({"screen": screen.pk, "name": screen.name, "source": found.get("source"),
                        "entry": found.get("entry"), "title": found.get("name"),
                        "layout": found.get("layout") or (f"message:{found['message']}" if "message" in found
                                                          else None),
                        "until": dt.datetime.fromtimestamp(end / 1000, tz=dt.UTC) if end else None})
        return Response(NowPlayingSerializer(out, many=True).data)


ROUTES = [
    (r"events/(?P<event_slug>[^/.]+)/playlists", PlaylistViewSet, "event-playlist"),
    (r"events/(?P<event_slug>[^/.]+)/schedules", ScheduleViewSet, "event-schedule"),
    (r"events/(?P<event_slug>[^/.]+)/overrides", OverrideViewSet, "event-override"),
    (r"events/(?P<event_slug>[^/.]+)/now-playing", NowPlayingViewSet, "event-now-playing"),
]
