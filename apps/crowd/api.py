# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API of occupancy: ``/api/v1/events/<slug>/occupancy/`` (areas with their count) and
``…/occupancy/<id>/count/`` for sensors (``{"delta"}``, ``{"in", "out"}`` or ``{"value"}``, optional ``"id"``)."""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.core import modules

from . import sensors
from .models import Area

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


class AreaSerializer(serializers.ModelSerializer):
    percent = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Area
        fields = ["id", "name", "room", "zone", "capacity", "busy_percent", "full_percent", "release_percent",
                  "value", "percent", "state", "state_since", "updated_at", "sensor_key"]
        read_only_fields = fields


class ReadingSerializer(serializers.Serializer):
    delta = serializers.IntegerField(required=False)
    value = serializers.IntegerField(required=False, min_value=0)
    id = serializers.CharField(required=False, max_length=64, allow_blank=True)
    device = serializers.CharField(required=False, max_length=80, allow_blank=True)

    def to_internal_value(self, data: Any) -> Any:
        # "in"/"out" are Python keywords: accept them alongside the declared fields
        out = super().to_internal_value(data)
        for key in ("in", "out"):
            v = data.get(key) if isinstance(data, dict) else None
            if v is not None:
                if isinstance(v, bool) or not isinstance(v, int):
                    raise serializers.ValidationError({key: "a whole number"})
                out[key] = v
        if not any(k in out for k in ("delta", "value", "in", "out")):
            raise serializers.ValidationError({"non_field_errors": ["send delta, in/out or value"]})
        return out


@EVENT_SLUG
class AreaViewSet(EventScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Areas with their live count. ``POST …/<id>/count/`` takes a sensor reading."""

    scope_module = "crowd"
    serializer_class = AreaSerializer
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "crowd.view", "HEAD": "crowd.view", "OPTIONS": "crowd.view",
                         "default": "crowd.count"}

    def get_event(self) -> Any:
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("crowd", event):
            raise NotFound("The occupancy module is switched off for this event.")
        return event

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return Area.objects.none()
        return Area.objects.filter(event=self.get_event())

    @extend_schema(request=ReadingSerializer, responses=AreaSerializer)
    @action(detail=True, methods=["post"])
    def count(self, request: Any, event_slug: str | None = None, pk: str | None = None) -> Response:
        area = self.get_object()
        data = ReadingSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        d = dict(data.validated_data)
        device = d.pop("device", "") or getattr(request.auth, "name", "") or "api"
        try:
            area = sensors.apply(area, d, source="sensor", device=str(device))
        except ValidationError as exc:
            raise ApiValidationError({"detail": exc.messages}) from None
        return Response(AreaSerializer(area).data)


ROUTES = [(r"events/(?P<event_slug>[^/.]+)/occupancy", AreaViewSet, "event-occupancy")]
