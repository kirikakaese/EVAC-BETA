# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API: ``/api/v1/events/<slug>/screens/`` and ``/api/v1/events/<slug>/screen-groups/``."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.core import modules
from apps.events import rbac
from apps.venues.models import Room, Venue, Zone

from . import services
from .models import Screen, ScreenGroup


class ScreenSerializer(serializers.ModelSerializer):
    venue = serializers.PrimaryKeyRelatedField(queryset=Venue.objects.all(), allow_null=True, required=False)
    zone = serializers.PrimaryKeyRelatedField(queryset=Zone.objects.all(), allow_null=True, required=False)
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), allow_null=True, required=False)
    groups = serializers.PrimaryKeyRelatedField(source="manual_groups", many=True, required=False,
                                                queryset=ScreenGroup.objects.all())
    health = serializers.SerializerMethodField()
    paired = serializers.BooleanField(source="is_paired", read_only=True)

    class Meta:
        model = Screen
        fields = ["id", "name", "description", "tags", "venue", "zone", "room", "groups", "floor",
                  "position_x", "position_y", "facing", "paired", "paired_at", "revoked_at", "last_seen_at",
                  "reported", "health", "token_prefix", "created_at", "updated_at"]
        read_only_fields = ["id", "paired", "paired_at", "revoked_at", "last_seen_at", "reported", "health",
                            "token_prefix", "created_at", "updated_at"]

    def get_health(self, obj) -> str:
        cfg = self.context.get("screen_cfg") or services.screen_settings(obj.event)
        return obj.health(heartbeat_seconds=cfg["heartbeat_seconds"], offline_after=cfg["offline_after_seconds"])

    def validate(self, attrs):
        event = self.context["event"]
        venues = set(event.venues.values_list("pk", flat=True))
        for key in ("venue", "zone", "room", "floor"):
            obj = attrs.get(key)
            if obj is not None and (obj.pk if key == "venue" else obj.venue_id) not in venues:
                raise serializers.ValidationError({key: "Not a venue of this event."})
        for g in attrs.get("manual_groups", []):
            if g.event_id != event.pk or g.kind != ScreenGroup.Kind.MANUAL:
                raise serializers.ValidationError({"groups": "Only manual groups of this event."})
        return attrs


class PairSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    screen = serializers.UUIDField(required=False, help_text="Re-pair this existing screen instead of creating one.")
    tags = serializers.ListField(child=serializers.CharField(max_length=40), required=False)


class ScreenGroupSerializer(serializers.ModelSerializer):
    match_venues = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Venue.objects.all())
    match_zones = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Zone.objects.all())
    match_rooms = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Room.objects.all())
    screens = serializers.SerializerMethodField()

    class Meta:
        model = ScreenGroup
        fields = ["id", "name", "description", "kind", "match_tags", "match_venues", "match_zones", "match_rooms",
                  "screens", "created_at", "updated_at"]
        read_only_fields = ["id", "screens", "created_at", "updated_at"]

    def get_screens(self, obj) -> list[str]:
        return [str(pk) for pk in obj.screens().values_list("pk", flat=True)]


class _ModuleMixin(EventScopedMixin):
    scope_module = "screens"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]

    def get_event(self):
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("screens", event):
            raise NotFound("The screens module is switched off for this event.")
        return event

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            ctx["event"] = self.get_event()
        return ctx

    def _visible(self, qs, perm="screens.view"):
        event = self.get_event()
        scopes = rbac.effective(self.request.user, event, request=self.request).access.scopes_for(perm)
        if scopes is None:
            return qs
        allowed = set(scopes)
        return qs.filter(pk__in=[o.pk for o in qs if allowed & set(o.evac_scope_chain())])

    def _require(self, perm, obj=None):
        if not rbac.has_perm(self.request.user, self.get_event(), perm, obj=obj, request=self.request):
            raise PermissionDenied(f"Missing permission {perm}.")


EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


@EVENT_SLUG
class ScreenViewSet(_ModuleMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                    mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Screens of an event. New screens are created by pairing (``POST …/pair/``)."""

    serializer_class = ScreenSerializer
    event_permissions = {"default": "screens.view"}
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Screen.objects.none()
        return self._visible(Screen.objects.filter(event=self.get_event()).prefetch_related("manual_groups"))

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if "event" in ctx:
            ctx["screen_cfg"] = services.screen_settings(ctx["event"])
        return ctx

    def perform_update(self, serializer):
        screen = serializer.instance
        self._require("screens.manage", screen)
        before = {f: getattr(screen, f) for f in ("name", "description", "venue", "zone", "room", "tags")}
        groups = serializer.validated_data.pop("manual_groups", None)
        for k, v in serializer.validated_data.items():
            setattr(screen, k, v)
        try:
            services.save_screen(screen, actor=self.request.user, request=self.request, before=before, groups=groups)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc

    def perform_destroy(self, instance):
        self._require("screens.manage", instance)
        services.delete_screen(instance, actor=self.request.user, request=self.request)

    @extend_schema(request=PairSerializer, responses={201: ScreenSerializer})
    @action(detail=False, methods=["post"])
    def pair(self, request, event_slug=None):
        """Claim the pairing code shown on a screen: creates the screen (or re-pairs ``screen``)."""
        self._require("screens.pair")
        data = PairSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        event = self.get_event()
        existing = None
        if data.validated_data.get("screen"):
            existing = Screen.objects.filter(event=event, pk=data.validated_data["screen"]).first()
            if existing is None:
                raise NotFound("No such screen.")
            self._require("screens.manage", existing)
        try:
            screen = services.pair(event, data.validated_data["code"], actor=request.user, request=request,
                                   screen=existing, name=data.validated_data.get("name", ""),
                                   tags=data.validated_data.get("tags", []))
        except ValidationError as exc:
            raise serializers.ValidationError({"code": exc.messages}) from exc
        return Response(self.get_serializer(screen).data, status=201)

    @extend_schema(request=None, responses={200: ScreenSerializer})
    @action(detail=True, methods=["post"])
    def revoke(self, request, event_slug=None, pk=None):
        """Revoke the device token: the screen stops and must be paired again."""
        screen = self.get_object()
        self._require("screens.manage", screen)
        services.revoke(screen, actor=request.user, request=request)
        screen.revoked_at = screen.revoked_at or timezone.now()
        return Response(self.get_serializer(screen).data)


@EVENT_SLUG
class ScreenGroupViewSet(_ModuleMixin, viewsets.ModelViewSet):
    serializer_class = ScreenGroupSerializer
    event_permissions = {"GET": "screens.view", "default": "screens.manage"}
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ScreenGroup.objects.none()
        return self._visible(ScreenGroup.objects.filter(event=self.get_event()).prefetch_related(
            "match_venues", "match_zones", "match_rooms"))

    def _save(self, group, data):
        m2m = {k: data.pop(k) for k in ("match_venues", "match_zones", "match_rooms") if k in data}
        venues = set(self.get_event().venues.values_list("pk", flat=True))
        for key, objs in m2m.items():
            if any((o.pk if key == "match_venues" else o.venue_id) not in venues for o in objs):
                raise serializers.ValidationError({key: "Not a venue of this event."})
        name = data.get("name", group.name)
        clash = ScreenGroup.objects.filter(event=self.get_event(), name__iexact=name)
        if not group._state.adding:
            clash = clash.exclude(pk=group.pk)
        if clash.exists():
            raise serializers.ValidationError({"name": "A group with this name exists already."})
        for k, v in data.items():
            setattr(group, k, v)
        return services.save_group(group, actor=self.request.user, request=self.request, m2m=m2m)

    def perform_create(self, serializer):
        serializer.instance = self._save(ScreenGroup(event=self.get_event()), dict(serializer.validated_data))

    def perform_update(self, serializer):
        self._require("screens.manage", serializer.instance)
        self._save(serializer.instance, dict(serializer.validated_data))

    def perform_destroy(self, instance):
        self._require("screens.manage", instance)
        services.delete_group(instance, actor=self.request.user, request=self.request)
