# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API: ``GET /api/v1/events/<slug>/evacuation/`` (state), ``GET .../evacuation/coverage/`` (screens reached,
latency) and ``POST .../evacuation/trigger/`` (ADR-0031).

Triggers from the API follow the policy of their source (default ``arm``), need ``evacuation.trigger`` (or
``evacuation.drill``) for the token's owner in a two-factor token, and accept an idempotency ``key``: a repeated
delivery returns the first result instead of raising a second alarm. The API cannot end alarms.
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.core import modules

from . import acks, machine, policy, services, triggers

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])
API_SOURCES = {policy.API, policy.BRIDGE}


class TriggerSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=[s.value for s in sorted(machine.ALARMS, key=machine.SEVERITY.__getitem__)])
    zone = serializers.UUIDField(required=False, allow_null=True)
    drill = serializers.BooleanField(default=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")
    key = serializers.CharField(required=False, allow_blank=True, max_length=100, default="",
                                help_text="Idempotency key: the same key never raises a second alarm.")
    source = serializers.CharField(required=False, default=policy.API, max_length=40,
                                   help_text="api (default), bridge or an extension's trigger source.")


def _status(s: machine.Status, labels: dict[str, str]) -> dict[str, Any]:
    return {"state": s.state.value, "label": labels[s.state.value], "drill": s.drill,
            "since": s.since.isoformat() if s.since else None,
            "clear_until": s.clear_until.isoformat() if s.clear_until else None}


@EVENT_SLUG
class EvacuationViewSet(EventScopedMixin, viewsets.ViewSet):
    scope_module = "evacuation"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"default": "evacuation.view"}

    def get_event(self) -> Any:
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("evacuation", event):
            raise NotFound("The evacuation module is switched off for this event.")
        return event

    @extend_schema(responses=inline_serializer("EvacuationState", {
        "model": serializers.CharField(), "event": serializers.DictField(), "zones": serializers.DictField(),
        "pending": serializers.ListField(child=serializers.DictField()),
        "blocked": serializers.ListField(child=serializers.CharField())}))
    def list(self, request: Request, event_slug: str | None = None) -> Response:
        event = self.get_event()
        cfg = services.config(event)
        now = timezone.now()
        ev, zones = services.statuses(event)
        return Response({
            "model": cfg.model.value,
            "event": _status(machine.current(ev, now), cfg.labels),
            "zones": {z: _status(machine.current(s, now), cfg.labels) for z, s in zones.items()},
            "pending": [{"id": str(r.pk), "kind": r.kind, "source": r.source, "state": r.state, "drill": r.drill,
                         "zone": str(r.zone_id) if r.zone_id else None,
                         "deadline": r.deadline.isoformat() if r.deadline else None}
                        for r in triggers.pending(event)],
            "blocked": sorted(services.blocked_ids(event)),
        })

    @extend_schema(request=TriggerSerializer, responses=inline_serializer("EvacuationTriggerResult", {
        "result": serializers.CharField(), "request": serializers.CharField(allow_null=True),
        "status": serializers.CharField(allow_null=True)}))
    @action(detail=False, methods=["post"])
    def trigger(self, request: Request, event_slug: str | None = None) -> Response:
        event = self.get_event()
        ser = TriggerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        from apps.core.registry import registry

        source = d["source"]
        if source not in API_SOURCES and source not in registry.ensure_loaded().evac_triggers:
            raise ValidationError({"source": "Unknown source for the API."})
        zone = None
        if d.get("zone"):
            zone = services.zones_of(event).filter(pk=d["zone"]).first()
            if zone is None:
                raise ValidationError({"zone": "Not a zone of this event."})
        try:
            out = triggers.trigger(event, d["state"], source=source, zone=zone, drill=d["drill"], actor=request.user,
                                   request=request, reason=d["reason"], key=d["key"])
        except machine.Refused as err:
            raise ValidationError({"detail": err.message, "code": err.code}) from err
        except DjangoPermissionDenied as err:
            raise PermissionDenied("You may not raise this alarm.") from err
        req = out.request
        return Response({"result": out.result, "request": str(req.pk) if req else None,
                         "status": req.status if req else None}, status=200 if out.result == "duplicate" else 201)


    @extend_schema(responses=inline_serializer("EvacuationCoverage", {
        "seq": serializers.IntegerField(), "total": serializers.IntegerField(),
        "confirmed": serializers.IntegerField(), "offline": serializers.IntegerField(),
        "pending": serializers.IntegerField(), "fallback": serializers.IntegerField(),
        "p95_ms": serializers.IntegerField(allow_null=True), "last_p95_ms": serializers.IntegerField(allow_null=True),
        "samples": serializers.IntegerField(), "zones": serializers.ListField(child=serializers.DictField()),
        "staff": serializers.ListField(child=serializers.DictField())}))
    @action(detail=False, methods=["get"])
    def coverage(self, request: Request, event_slug: str | None = None) -> Response:
        """Screens that confirmed the current message ("X of Y confirmed / Z offline"), per zone, and the
        trigger-to-render time (p95); staff answers to the running alarm."""
        event = self.get_event()
        cov = acks.coverage(event)
        since = acks.alarm_since(event)
        return Response({
            "seq": cov.seq, "total": cov.total, "confirmed": cov.confirmed, "offline": cov.offline,
            "pending": cov.pending, "fallback": cov.fallback, "p95_ms": cov.p95_ms, "last_p95_ms": cov.last_p95_ms,
            "samples": cov.samples, "zones": cov.zones,
            "staff": [{"kind": a.kind, "user": a.user_repr, "zone": str(a.zone_id) if a.zone_id else None,
                       "note": a.note, "drill": a.drill, "at": a.at.isoformat()}
                      for a in (acks.recent_staff(event, since) if since else [])],
        })


ROUTES = [(r"events/(?P<event_slug>[^/.]+)/evacuation", EvacuationViewSet, "event-evacuation")]
