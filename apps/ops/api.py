# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API of operations: incidents (``/api/v1/events/<slug>/incidents/``, with ``status``/``note`` actions) and
the ops log (``…/ops-log/``), e.g. for a radio dispatcher's tool or a script that files incidents from a sensor."""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.core import modules

from . import services
from .models import Incident, LogEntry

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


class IncidentSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source="zone.name", read_only=True, default="")
    room_name = serializers.CharField(source="room.name", read_only=True, default="")
    assignee_name = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = ["id", "number", "title", "description", "category", "severity", "status", "zone", "zone_name",
                  "room", "room_name", "location", "assignee", "assignee_name", "team", "reported_by", "links",
                  "source", "external_id", "created_at", "acknowledged_at", "resolved_at", "closed_at", "version"]
        read_only_fields = ["id", "number", "status", "links", "created_at", "acknowledged_at", "resolved_at",
                            "closed_at", "version"]

    def get_assignee_name(self, obj: Incident) -> str:
        return str(obj.assignee) if obj.assignee_id else ""

    def validate_category(self, value: str) -> str:
        cats = services.categories(self.context["event"])
        if value not in cats:
            raise serializers.ValidationError(f"One of: {', '.join(cats)}")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        event = self.context["event"]
        for key in ("zone", "room"):
            obj = attrs.get(key)
            if obj is not None and not event.venues.filter(pk=obj.venue_id).exists():
                raise serializers.ValidationError({key: "Not part of this event's venues."})
        user = attrs.get("assignee")
        if user is not None and not user.memberships.filter(event=event).exists():
            raise serializers.ValidationError({"assignee": "Not a member of this event."})
        return attrs


class StatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Incident.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class NoteSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000)


class LogEntrySerializer(serializers.ModelSerializer):
    incident_number = serializers.IntegerField(source="incident.number", read_only=True, default=None)

    class Meta:
        model = LogEntry
        fields = ["id", "at", "kind", "sender", "recipient", "text", "important", "incident", "incident_number",
                  "source", "client_id"]
        read_only_fields = ["id", "at", "kind", "source", "incident_number"]


class _OpsMixin(EventScopedMixin):
    scope_module = "ops"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]

    def get_event(self) -> Any:
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("ops", event):
            raise NotFound("The incidents module is switched off for this event.")
        return event

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            ctx["event"] = self.get_event()
        return ctx


@EVENT_SLUG
class IncidentViewSet(_OpsMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Incidents (``?status=open`` for new/acknowledged/in progress)."""

    serializer_class = IncidentSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    event_permissions = {"GET": "ops.view", "HEAD": "ops.view", "OPTIONS": "ops.view", "POST": "ops.report",
                         "default": "ops.manage"}

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return Incident.objects.none()
        qs = Incident.objects.filter(event=self.get_event()).select_related("zone", "room", "assignee")
        st = self.request.query_params.get("status")
        if st == "open":
            qs = qs.filter(status__in=Incident.OPEN)
        elif st:
            qs = qs.filter(status=st)
        return qs

    def perform_create(self, serializer: Any) -> None:
        inc = Incident(event=self.get_event(), source="api", **serializer.validated_data)
        try:
            services.create_incident(inc, actor=self.request.user, request=self.request)
        except ValidationError as exc:
            raise ApiValidationError({"detail": exc.messages}) from None
        serializer.instance = inc

    def perform_update(self, serializer: Any) -> None:
        inc = serializer.instance
        before = {f: getattr(inc, f) for f in services.EDITABLE}
        for k, v in serializer.validated_data.items():
            setattr(inc, k, v)
        changed = [k for k in serializer.validated_data if before.get(k) != getattr(inc, k)]
        try:
            services.update_incident(inc, changed, actor=self.request.user, request=self.request, before=before)
        except ValidationError as exc:
            raise ApiValidationError({"detail": exc.messages}) from None

    @extend_schema(request=StatusSerializer, responses=IncidentSerializer)
    @action(detail=True, methods=["post"])
    def status(self, request: Any, event_slug: str | None = None, pk: str | None = None) -> Response:
        inc = self.get_object()
        data = StatusSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.set_status(inc, data.validated_data["status"], actor=request.user, request=request,
                                note=data.validated_data.get("note", ""))
        except ValidationError as exc:
            raise ApiValidationError({"detail": exc.messages}) from None
        return Response(IncidentSerializer(inc, context=self.get_serializer_context()).data)

    @extend_schema(request=NoteSerializer, responses=IncidentSerializer)
    @action(detail=True, methods=["post"])
    def note(self, request: Any, event_slug: str | None = None, pk: str | None = None) -> Response:
        inc = self.get_object()
        data = NoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.add_note(inc, data.validated_data["text"], actor=request.user, request=request)
        return Response(IncidentSerializer(inc, context=self.get_serializer_context()).data)


@EVENT_SLUG
class LogEntryViewSet(_OpsMixin, mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """The ops log, newest first. ``POST`` writes an entry (``client_id`` makes a retry harmless)."""

    serializer_class = LogEntrySerializer
    event_permissions = {"GET": "ops.view", "HEAD": "ops.view", "OPTIONS": "ops.view", "default": "ops.report"}

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return LogEntry.objects.none()
        return LogEntry.objects.filter(event=self.get_event()).select_related("incident")

    def perform_create(self, serializer: Any) -> None:
        d = serializer.validated_data
        inc = d.get("incident")
        if inc is not None and inc.event_id != self.get_event().pk:
            raise ApiValidationError({"incident": "Not an incident of this event."})
        try:
            serializer.instance = services.add_entry(
                self.get_event(), d["text"], actor=self.request.user, sender=d.get("sender", ""),
                recipient=d.get("recipient", ""), important=d.get("important", False), incident=inc,
                client_id=d.get("client_id", ""), request=self.request)
        except ValidationError as exc:
            raise ApiValidationError({"detail": exc.messages}) from None


ROUTES = [(r"events/(?P<event_slug>[^/.]+)/incidents", IncidentViewSet, "event-incident"),
          (r"events/(?P<event_slug>[^/.]+)/ops-log", LogEntryViewSet, "event-ops-log")]
