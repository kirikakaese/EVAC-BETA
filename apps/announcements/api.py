# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API: ``/api/v1/events/<slug>/announcements/`` (+ submit/approve/reject/cancel), levels and templates."""
from __future__ import annotations

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.core import modules
from apps.screens.models import Screen, ScreenGroup
from apps.venues.models import Room, Venue, Zone

from . import services
from .models import Announcement, Delivery, Level, Template

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])
M2M = ("venues", "zones", "rooms", "screen_groups", "screens")


class _Mixin(EventScopedMixin):
    scope_module = "announcements"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "announcements.view", "HEAD": "announcements.view",
                         "OPTIONS": "announcements.view", "default": "announcements.view"}

    def get_event(self):
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False):
            if not modules.is_enabled("announcements", event):
                raise NotFound("The announcements module is switched off for this event.")
            services.ensure_defaults(event)
        return event

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["event"] = self.get_event()
        return ctx


class EventRelated(serializers.PrimaryKeyRelatedField):
    def __init__(self, model, field="event", **kwargs):
        self.model, self.field = model, field
        super().__init__(**kwargs)

    def get_queryset(self):
        event = self.context.get("event")
        if event is None or not event.pk:
            return self.model.objects.none()
        return self.model.objects.filter(**{self.field: event})


class LevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = ["id", "key", "name", "rank", "colour", "display", "sound", "min_display_seconds",
                  "repeat_every_minutes", "default_channels", "requires_approval", "emergency"]
        read_only_fields = fields


class TemplateSerializer(serializers.ModelSerializer):
    level = serializers.SlugRelatedField(slug_field="key", read_only=True)
    variables = serializers.SerializerMethodField()

    class Meta:
        model = Template
        fields = ["id", "name", "level", "title", "body", "short", "variables"]
        read_only_fields = fields

    def get_variables(self, obj) -> list[str]:
        return services.variables_in(obj.title, obj.body, obj.short)


class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = ["id", "channel", "occurrence", "status", "recipients", "detail", "attempts", "sent_at"]
        read_only_fields = fields


class AnnouncementSerializer(serializers.ModelSerializer):
    level = serializers.SlugRelatedField(slug_field="key", queryset=Level.objects.none())
    template = EventRelated(Template, required=False, allow_null=True)
    venues = EventRelated(Venue, field="events", many=True, required=False)
    zones = EventRelated(Zone, field="venue__events", many=True, required=False)
    rooms = EventRelated(Room, field="venue__events", many=True, required=False)
    screen_groups = EventRelated(ScreenGroup, many=True, required=False)
    screens = EventRelated(Screen, many=True, required=False)
    deliveries = DeliverySerializer(many=True, read_only=True)
    send = serializers.BooleanField(write_only=True, required=False, default=False,
                                    help_text="Submit at once (published or into the approval queue).")

    class Meta:
        model = Announcement
        fields = ["id", "level", "template", "variables", "title", "body", "short", "all_screens", *M2M,
                  "channels", "channel_texts", "audiences", "starts_at", "anchor", "anchor_edge", "anchor_offset",
                  "anchor_label", "ends_at", "recurrence", "recurrence_until", "status",
                  "decision_note", "published_at", "speech_status", "deliveries", "send", "created_at"]
        read_only_fields = ["id", "status", "decision_note", "published_at", "speech_status", "deliveries",
                            "created_at", "anchor_label"]
        extra_kwargs = {"title": {"required": False}, "starts_at": {"required": False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        event = self.context.get("event")
        if event is not None and event.pk:
            self.fields["level"].queryset = Level.objects.filter(event=event)

    def validate_variables(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("An object of names and texts.")
        return value

    def validate_channel_texts(self, value):
        if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            raise serializers.ValidationError("An object of channel keys and texts.")
        return value

    def validate_audiences(self, value):
        if not isinstance(value, list) or not all(isinstance(a, str) for a in value):
            raise serializers.ValidationError("A list of audience keys, e.g. \"roles:<id>\".")
        return value

    def validate_channels(self, value):
        if not isinstance(value, list) or not all(isinstance(c, str) for c in value):
            raise serializers.ValidationError("A list of channel keys.")
        return value


@EVENT_SLUG
class LevelViewSet(_Mixin, viewsets.ReadOnlyModelViewSet):
    """Priority levels of the event (edited in the portal)."""

    serializer_class = LevelSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Level.objects.none()
        return Level.objects.filter(event=self.get_event())


@EVENT_SLUG
class TemplateViewSet(_Mixin, viewsets.ReadOnlyModelViewSet):
    """Announcement templates; ``variables`` lists the names a template asks for."""

    serializer_class = TemplateSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Template.objects.none()
        return Template.objects.filter(event=self.get_event()).select_related("level")


@EVENT_SLUG
class AnnouncementViewSet(_Mixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                          mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Announcements. Create writes a draft (``send: true`` submits it at once); with a ``template`` its texts
    are filled from ``variables``. ``POST …/submit/``, ``…/approve/``, ``…/reject/``, ``…/cancel/``.
    ``deliveries`` is the delivery report (one row per channel and occurrence)."""

    serializer_class = AnnouncementSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["status"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Announcement.objects.none()
        return (Announcement.objects.filter(event=self.get_event()).select_related("level")
                .prefetch_related("deliveries", *M2M))

    def _save(self, serializer, ann: Announcement):
        d = dict(serializer.validated_data)
        send = d.pop("send", False)
        m2m = {k: d.pop(k) for k in M2M if k in d}
        template = d.pop("template", None)
        variables = d.pop("variables", None)
        for k, v in d.items():
            setattr(ann, k, v)
        if template is not None:
            services.apply_template(ann, template, variables or {})
        elif variables is not None:
            ann.variables = variables
        if not ann.channels:
            ann.channels = list(ann.level.default_channels) if ann.level_id else []
        if m2m and "all_screens" not in d:
            ann.all_screens = False
        try:
            services.save_draft(ann, actor=self.request.user, request=self.request, m2m=m2m)
            if send:
                services.submit(ann, actor=self.request.user, request=self.request)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc) or None) from exc
        serializer.instance = ann

    def perform_create(self, serializer):
        self._save(serializer, Announcement(event=self.get_event()))

    def perform_update(self, serializer):
        self._save(serializer, serializer.instance)

    def _act(self, fn, **kwargs):
        ann = self.get_object()
        try:
            fn(ann, actor=self.request.user, request=self.request, **kwargs)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc) or None) from exc
        ann.refresh_from_db()
        return Response(self.get_serializer(ann).data)

    @extend_schema(request=None, responses={200: AnnouncementSerializer})
    @action(detail=True, methods=["post"])
    def submit(self, request, event_slug=None, pk=None):
        return self._act(services.submit)

    @extend_schema(request=None, responses={200: AnnouncementSerializer})
    @action(detail=True, methods=["post"])
    def approve(self, request, event_slug=None, pk=None):
        return self._act(services.approve, note=str(request.data.get("note", "")))

    @extend_schema(request=None, responses={200: AnnouncementSerializer})
    @action(detail=True, methods=["post"])
    def reject(self, request, event_slug=None, pk=None):
        return self._act(services.reject, note=str(request.data.get("note", "")))

    @extend_schema(request=None, responses={200: AnnouncementSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, event_slug=None, pk=None):
        return self._act(services.cancel)


ROUTES = [
    (r"events/(?P<event_slug>[^/.]+)/announcements", AnnouncementViewSet, "event-announcement"),
    (r"events/(?P<event_slug>[^/.]+)/announcement-levels", LevelViewSet, "event-announcement-level"),
    (r"events/(?P<event_slug>[^/.]+)/announcement-templates", TemplateViewSet, "event-announcement-template"),
]
