# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API of the program: ``/api/v1/events/<slug>/sessions/`` (read) and ``…/sessions/<id>/live/`` (delay, cancel,
move, restore), e.g. for a stage manager's tablet or a script."""
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

from . import services
from .models import Session, Stage

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


class SessionSerializer(serializers.ModelSerializer):
    stage_name = serializers.CharField(source="stage.name", read_only=True, default="")
    track_name = serializers.CharField(source="track.name", read_only=True, default="")
    speaker_names = serializers.SerializerMethodField()
    delay_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Session
        fields = ["id", "title", "subtitle", "abstract", "language", "kind", "url", "stage", "stage_name", "track",
                  "track_name", "speaker_names", "starts_at", "ends_at", "planned_start", "planned_end", "status",
                  "delay_minutes", "note", "public", "source", "external_id", "overrides", "version"]
        read_only_fields = fields

    def get_speaker_names(self, obj: Session) -> list[str]:
        return [p.name for p in obj.speakers.all()]


class LiveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["delay", "cancel", "move", "restore"])
    minutes = serializers.IntegerField(required=False)
    stage = serializers.UUIDField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=200)
    shift_following = serializers.BooleanField(required=False, default=False)


@EVENT_SLUG
class SessionViewSet(EventScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Sessions of the event (``?day=YYYY-MM-DD`` limits to one day in the event time zone)."""

    scope_module = "program"
    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "program.view", "HEAD": "program.view", "OPTIONS": "program.view",
                         "default": "program.live"}

    def get_event(self) -> Any:
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("program", event):
            raise NotFound("The program module is switched off for this event.")
        return event

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return Session.objects.none()
        qs = Session.objects.filter(event=self.get_event()).select_related("stage", "track").prefetch_related(
            "speakers")
        day = self.request.query_params.get("day")
        if day:
            import datetime as dt

            from .views import _tz

            try:
                d = dt.date.fromisoformat(day)
            except ValueError:
                raise ApiValidationError({"day": "YYYY-MM-DD"}) from None
            start = dt.datetime.combine(d, dt.time(0), _tz(self.get_event()))
            qs = qs.filter(starts_at__lt=start + dt.timedelta(days=1), ends_at__gt=start)
        return qs

    @extend_schema(request=LiveSerializer, responses=SessionSerializer)
    @action(detail=True, methods=["post"])
    def live(self, request: Any, event_slug: str | None = None, pk: str | None = None) -> Response:
        s = self.get_object()
        data = LiveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        note = v.get("note") or None
        try:
            if v["action"] == "delay":
                services.delay(s, int(v.get("minutes") or 0), actor=request.user, request=request, note=note,
                               shift_following=v.get("shift_following", False))
            elif v["action"] == "cancel":
                services.cancel(s, actor=request.user, request=request, note=note)
            elif v["action"] == "move":
                stage = Stage.objects.filter(event=s.event, pk=v["stage"]).first() if v.get("stage") else None
                if v.get("stage") and stage is None:
                    raise ValidationError("Unknown stage.")
                services.move(s, stage, actor=request.user, request=request, note=note)
            else:
                services.restore(s, actor=request.user, request=request)
        except ValidationError as exc:
            raise ApiValidationError({"detail": exc.messages}) from None
        s.refresh_from_db()
        return Response(SessionSerializer(s).data)


ROUTES = [(r"events/(?P<event_slug>[^/.]+)/sessions", SessionViewSet, "event-session")]
