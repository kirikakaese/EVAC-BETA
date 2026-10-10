# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API of access: ``/api/v1/events/<slug>/attendees/`` (create, edit), ``…/ticket-types/``,
``…/access-zones/`` and ``POST …/access-zones/<id>/scan/`` for hardware scanners (``{code, direction, id}``)."""
from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import PermissionDenied as ApiPermissionDenied
from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.core import modules
from apps.events import rbac

from . import services
from .models import AccessZone, Attendee, TicketType

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


class TicketTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketType
        fields = ["id", "name", "colour", "zones", "source", "external_id"]
        read_only_fields = fields


class AccessZoneSerializer(serializers.ModelSerializer):
    inside = serializers.SerializerMethodField()

    class Meta:
        model = AccessZone
        fields = ["id", "name", "open_to_all", "checkin", "reentry", "room", "area_id", "inside"]
        read_only_fields = fields

    def get_inside(self, obj: AccessZone) -> int:
        return obj.presence.filter(inside=True).count()


class AttendeeSerializer(serializers.ModelSerializer):
    ticket_type_name = serializers.CharField(source="ticket_type.name", read_only=True)

    class Meta:
        model = Attendee
        fields = ["id", "name", "email", "company", "ticket_type", "ticket_type_name", "code", "status",
                  "checked_in_at", "source", "external_id"]
        read_only_fields = ["id", "ticket_type_name", "checked_in_at", "source"]
        extra_kwargs = {"code": {"required": False, "allow_blank": True}}

    def validate_ticket_type(self, value: TicketType) -> TicketType:
        if value.event_id != self.context["event"].pk:
            raise serializers.ValidationError("Unknown ticket type.")
        return value


class _AccessMixin(EventScopedMixin):
    scope_module = "access"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "access.view", "HEAD": "access.view", "OPTIONS": "access.view",
                         "default": "access.manage"}

    def get_event(self) -> Any:
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("access", event):
            raise NotFound("The access module is switched off for this event.")
        return event


@EVENT_SLUG
class AttendeeViewSet(_AccessMixin, viewsets.ModelViewSet):
    """Attendees (``?search=``, ``?status=valid``, ``?ticket_type=``). ``POST`` adds one (an empty code gets a
    random one), ``PATCH`` edits."""

    serializer_class = AttendeeSerializer
    filterset_fields = ["status", "ticket_type", "source"]
    search_fields = ["name", "email", "company", "code"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return Attendee.objects.none()
        return Attendee.objects.filter(event=self.get_event()).select_related("ticket_type")

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            ctx["event"] = self.get_event()
        return ctx

    def perform_create(self, serializer: Any) -> None:
        a = Attendee(event=self.get_event(), **serializer.validated_data)
        from django.core.exceptions import ValidationError

        try:
            services.save_attendee(a, actor=self.request.user, request=self.request)
        except ValidationError as err:
            raise ApiValidationError({"non_field_errors": err.messages}) from None
        serializer.instance = a

    def perform_update(self, serializer: Any) -> None:
        from django.core.exceptions import ValidationError

        a = serializer.instance
        for k, v in serializer.validated_data.items():
            setattr(a, k, v)
        try:
            services.save_attendee(a, actor=self.request.user, request=self.request)
        except ValidationError as err:
            raise ApiValidationError({"non_field_errors": err.messages}) from None


@EVENT_SLUG
class TicketTypeViewSet(_AccessMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = TicketTypeSerializer

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return TicketType.objects.none()
        return TicketType.objects.filter(event=self.get_event()).prefetch_related("zones")


@EVENT_SLUG
class AccessZoneViewSet(_AccessMixin, viewsets.ReadOnlyModelViewSet):
    """Access zones with how many are inside; ``POST …/<id>/scan/`` scans a ticket (hardware scanners, turnstiles;
    permission ``access.scan``)."""

    serializer_class = AccessZoneSerializer
    event_permissions = {**_AccessMixin.event_permissions, "POST": "access.scan"}

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return AccessZone.objects.none()
        return AccessZone.objects.filter(event=self.get_event())

    @extend_schema(request=inline_serializer("ScanRequest", {
        "code": serializers.CharField(), "direction": serializers.ChoiceField(["in", "out"], required=False),
        "id": serializers.CharField(required=False), "device": serializers.CharField(required=False)}),
        responses={200: inline_serializer("ScanResult", {
            "result": serializers.CharField(), "message": serializers.CharField(),
            "name": serializers.CharField(allow_blank=True)})})
    @action(detail=True, methods=["post"])
    def scan(self, request: Any, event_slug: str | None = None, pk: str | None = None) -> Response:
        zone = self.get_object()
        if not rbac.has_perm(request.user, zone.event, "access.scan", obj=zone, request=request):
            raise ApiPermissionDenied("access.scan")
        code = str(request.data.get("code") or "")
        if not code:
            raise ApiValidationError({"code": "required"})
        s, message = services.scan(zone, code, direction=str(request.data.get("direction") or "in"),
                                   actor=request.user, client_id=str(request.data.get("id") or ""),
                                   device=str(request.data.get("device") or "api"), source="api")
        return Response({"result": s.result, "message": message, "name": s.attendee.name if s.attendee else ""})


ROUTES = [(r"events/(?P<event_slug>[^/.]+)/attendees", AttendeeViewSet, "event-attendee"),
          (r"events/(?P<event_slug>[^/.]+)/ticket-types", TicketTypeViewSet, "event-ticket-type"),
          (r"events/(?P<event_slug>[^/.]+)/access-zones", AccessZoneViewSet, "event-access-zone")]
