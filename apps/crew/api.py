# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API of crew: ``/api/v1/events/<slug>/shifts/`` (``?day=``, ``…/needed/``) and ``…/crew-teams/``."""
from __future__ import annotations

import datetime as dt
from typing import Any

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

from . import services
from .models import Assignment, Shift, Team

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ["id", "name", "description", "colour", "meeting_point", "source", "external_id"]
        read_only_fields = fields


class ShiftSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    place = serializers.CharField(read_only=True)
    filled = serializers.SerializerMethodField()
    people = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = ["id", "team", "team_name", "title", "place", "starts_at", "ends_at", "needed", "filled", "people",
                  "open_signup", "source", "external_id"]
        read_only_fields = fields

    def get_filled(self, obj: Shift) -> int:
        return obj.assignments.filter(status__in=Assignment.ACTIVE).count()

    def get_people(self, obj: Shift) -> list[dict[str, str]]:
        return [{"name": a.member.name, "status": a.status} for a in obj.assignments.select_related("member")]


class _CrewMixin(EventScopedMixin):
    scope_module = "crew"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "crew.view", "HEAD": "crew.view", "OPTIONS": "crew.view", "default": "crew.manage"}

    def get_event(self) -> Any:
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("crew", event):
            raise NotFound("The crew module is switched off for this event.")
        return event


@EVENT_SLUG
class ShiftViewSet(_CrewMixin, viewsets.ReadOnlyModelViewSet):
    """Shifts with how many are filled (``?day=YYYY-MM-DD`` in the event time zone)."""

    serializer_class = ShiftSerializer

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return Shift.objects.none()
        event = self.get_event()
        qs = Shift.objects.filter(event=event).select_related("team", "room")
        day = self.request.query_params.get("day")
        if day:
            try:
                d = dt.date.fromisoformat(day)
            except ValueError:
                raise ApiValidationError({"day": "YYYY-MM-DD"}) from None
            start = dt.datetime.combine(d, dt.time(0), services._tz(event))
            qs = qs.filter(starts_at__lt=start + dt.timedelta(days=1), ends_at__gt=start)
        return qs

    @extend_schema(responses={200: {"type": "array", "items": {"type": "object"}}})
    @action(detail=False)
    def needed(self, request: Any, event_slug: str | None = None) -> Response:
        """Shifts now and soon that still need people."""
        return Response(services.needed_now(self.get_event()))


@EVENT_SLUG
class TeamViewSet(_CrewMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = TeamSerializer

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return Team.objects.none()
        return Team.objects.filter(event=self.get_event())


ROUTES = [(r"events/(?P<event_slug>[^/.]+)/shifts", ShiftViewSet, "event-shift"),
          (r"events/(?P<event_slug>[^/.]+)/crew-teams", TeamViewSet, "event-crew-team")]
