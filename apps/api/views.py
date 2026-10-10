# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API v1 (core): events, members, roles, modules, audit, venues, tokens, extensions, registry."""
from __future__ import annotations

import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import ServiceToken
from apps.core import modules
from apps.core.audit import log, verify_chain
from apps.core.models import AuditLog
from apps.core.registry import registry
from apps.events import rbac, services
from apps.events.models import Event, Membership, Role
from apps.extensions import services as ext_services
from apps.extensions.models import ExtensionConfig, InboundDelivery
from apps.venues import access as venue_access
from apps.venues import graph as venue_graph
from apps.venues.models import Building, Edge, Floor, Point, Room, Venue, Zone

from . import serializers as s
from .permissions import EventPermission, HasScope, IsSuperuser


@extend_schema(responses={200: dict}, auth=[])
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness and version information (no authentication)."""
    return Response({"status": "ok", "version": __import__("evac").__version__, "mode": settings.EVAC_MODE})


@extend_schema(responses=s.UserSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    data = s.UserSerializer(request.user).data
    tok = getattr(request, "service_token", None)
    data["token"] = ({"name": tok.name, "scopes": tok.scopes, "event": tok.event.slug if tok.event_id else None}
                     if tok else None)
    data["events"] = [{"slug": e.slug, "name": e.name, "state": e.state}
                      for e in Event.objects.visible_to(request.user)]
    return Response(data)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def registry_view(request):
    """What this instance provides: modules, permissions, scope kinds, webhook events, extensions, data
    sources, widgets, notification channels and evacuation triggers."""
    reg = registry.ensure_loaded()
    return Response({
        "plugins": [{"key": p.key, "name": p.name, "version": p.version, "kind": p.kind} for p in reg.plugins.values()],
        "modules": [{"key": m.key, "name": m.name, "required": m.required, "depends_on": list(m.depends_on)}
                    for m in reg.modules.values()],
        "permissions": [{"key": p.key, "label": p.label, "scopes": list(p.scopes), "sensitive": p.sensitive}
                        for p in reg.permissions.values()],
        "scope_kinds": [{"key": k.key, "label": k.label} for k in reg.scope_kinds.values()],
        "webhook_events": [{"key": w.key, "description": w.description} for w in reg.webhook_events.values()],
        "extensions": [{"key": e.key, "name": e.name, "version": e.version, "scope": e.scope}
                       for e in reg.extensions.values()],
        "data_sources": [{"key": d.key, "name": d.name, "mode": d.mode} for d in reg.data_sources.values()],
        "widgets": [{"key": w.key, "name": w.name, "version": w.version} for w in reg.widgets.values()],
        "notification_channels": [{"key": c.key, "name": c.name} for c in reg.notification_channels.values()],
        "evac_triggers": [{"key": t.key, "name": t.name} for t in reg.evac_triggers.values()],
    })


class EventScopedMixin:
    """For viewsets nested below /events/<event_slug>/."""

    def get_event(self) -> Event:
        if getattr(self, "swagger_fake_view", False):
            return Event()
        if not hasattr(self, "_event"):
            event = get_object_or_404(Event.objects.visible_to(self.request.user), slug=self.kwargs["event_slug"])
            tok = getattr(self.request, "service_token", None)
            if tok is not None and tok.event_id and tok.event_id != event.pk:
                raise PermissionDenied("This token is bound to another event.")
            self._event = event
        return self._event


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = s.EventSerializer
    lookup_field = "slug"
    scope_module = "events"
    filterset_fields = ["state"]
    search_fields = ["name", "slug"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Event.objects.visible_to(self.request.user).prefetch_related("venues")
        tok = getattr(self.request, "service_token", None)
        if tok is not None and tok.event_id:
            qs = qs.filter(pk=tok.event_id)
        return qs

    def get_event(self):
        return self.get_object()

    def _require(self, perm):
        event = self.get_object()
        if not rbac.has_perm(self.request.user, event, perm, request=self.request):
            raise PermissionDenied(f"Missing permission {perm}.")
        return event

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Only instance admins create events.")
        data = dict(serializer.validated_data)
        venues = data.pop("venues", [])
        event = services.create_event(user=self.request.user, request=self.request, **data)
        event.venues.set(venues)
        serializer.instance = event

    def perform_update(self, serializer):
        event = self._require("events.manage")
        before = {k: getattr(event, k) for k in serializer.validated_data if k != "venues"}
        obj = serializer.save()
        log(action="event.updated", actor=self.request.user, target=obj, event=obj, request=self.request,
            changes={k: [before[k], getattr(obj, k)] for k in before if before[k] != getattr(obj, k)})
        from apps.core.webhooks import emit

        emit("event.updated", {"slug": obj.slug}, event=obj)

    @extend_schema(request=s.TransitionSerializer, responses=s.EventSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, slug=None):
        target = s.TransitionSerializer(data=request.data)
        target.is_valid(raise_exception=True)
        perm = "events.delete" if target.validated_data["state"] == "archived" else "events.manage"
        event = self._require(perm)
        try:
            event.transition(target.validated_data["state"], user=request.user, request=request,
                             reason=target.validated_data.get("reason", ""))
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(s.EventSerializer(event).data)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"])
    def export(self, request, slug=None):
        event = self._require("events.manage")
        log(action="event.exported", actor=request.user, target=event, event=event, request=request)
        return Response(services.export_event(event))

    @extend_schema(request=s.CloneSerializer, responses=s.EventSerializer)
    @action(detail=True, methods=["post"])
    def clone(self, request, slug=None):
        if not request.user.is_superuser:
            raise PermissionDenied("Only instance admins create events.")
        src = self.get_object()
        data = s.CloneSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        dst = services.clone_event(src, user=request.user, request=request, **data.validated_data)
        return Response(s.EventSerializer(dst).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=dict, responses=s.EventSerializer)
    @action(detail=False, methods=["post"], url_path="import")
    def import_(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied("Only instance admins create events.")
        try:
            event, report = services.import_event(request.data.get("data") or request.data,
                                                  slug=request.data.get("slug", "") if "data" in request.data else "",
                                                  user=request.user, request=request)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({**s.EventSerializer(event).data, "report": report}, status=status.HTTP_201_CREATED)


class RoleViewSet(EventScopedMixin, viewsets.ModelViewSet):
    serializer_class = s.RoleSerializer
    scope_module = "events"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "events.members", "default": "events.roles"}
    lookup_field = "key"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Role.objects.none()
        return Role.objects.filter(event=self.get_event())

    def perform_create(self, serializer):
        role = Role(event=self.get_event(), **serializer.validated_data)
        serializer.instance = services.save_role(role, actor=self.request.user, request=self.request)

    def perform_update(self, serializer):
        role = serializer.instance
        before = {"name": role.name, "permissions": list(role.permissions), "require_2fa": role.require_2fa}
        for k, v in serializer.validated_data.items():
            setattr(role, k, v)
        services.save_role(role, actor=self.request.user, request=self.request, before=before)

    def perform_destroy(self, instance):
        if instance.builtin:
            raise PermissionDenied("Built-in roles cannot be deleted.")
        log(action="role.deleted", actor=self.request.user, target=instance, event=instance.event,
            request=self.request, message=f"Role {instance.name} deleted")
        instance.delete()


class MemberViewSet(EventScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                    viewsets.GenericViewSet):
    serializer_class = s.MembershipSerializer
    scope_module = "events"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"default": "events.members"}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Membership.objects.none()
        return (Membership.objects.filter(event=self.get_event()).select_related("user")
                .prefetch_related("assignments__role"))

    def perform_destroy(self, instance):
        try:
            services.remove_member(instance, actor=self.request.user, request=self.request)
        except ValidationError as exc:
            raise PermissionDenied(exc.messages[0])

    @extend_schema(request=s.AssignRoleSerializer, responses={201: dict})
    @action(detail=False, methods=["post"])
    def assign(self, request, event_slug=None):
        """Give a role to a user by e-mail (optionally scoped); invites unknown addresses."""
        data = s.AssignRoleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        event = self.get_event()
        role = get_object_or_404(Role, event=event, key=data.validated_data["role"])
        if role.grants_sensitive and not rbac.has_perm(request.user, event, "events.roles", request=request):
            raise PermissionDenied("Assigning this role needs the events.roles permission.")
        user = get_user_model().objects.filter(email__iexact=data.validated_data["email"]).first()
        sk, sid = data.validated_data["scope_kind"], data.validated_data["scope_id"]
        try:
            if user is None:
                if not data.validated_data["invite"]:
                    return Response({"detail": "No account with this e-mail."}, status=404)
                inv, _url = services.invite(event, data.validated_data["email"], role, actor=request.user,
                                            request=request, scope_kind=sk, scope_id=sid)
                return Response({"invited": inv.email}, status=201)
            services.assign_role(event, user, role, scope_kind=sk, scope_id=sid, actor=request.user, request=request)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response({"assigned": user.email, "role": role.key}, status=201)


@extend_schema(parameters=[OpenApiParameter("id", str, OpenApiParameter.PATH, description="Module key")])
class ModuleViewSet(EventScopedMixin, viewsets.ViewSet):
    scope_module = "events"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "events.view", "default": "modules.manage"}
    serializer_class = s.ModuleStateSerializer

    def _rows(self, event):
        return [{"key": r["spec"].key, "name": r["spec"].name, "description": r["spec"].description,
                 "required": r["spec"].required, "instance": r["instance"], "event": r["event"],
                 "active": r["active"]} for r in modules.status(event)]

    @extend_schema(responses=s.ModuleStateSerializer(many=True))
    def list(self, request, event_slug=None):
        return Response(self._rows(self.get_event()))

    @extend_schema(request=s.ModuleStateSerializer, responses=s.ModuleStateSerializer(many=True))
    def partial_update(self, request, event_slug=None, pk=None):
        event = self.get_event()
        spec = registry.ensure_loaded().modules.get(pk)
        if spec is None:
            return Response({"detail": "Unknown module."}, status=404)
        try:
            modules.set_event(event, pk, request.data.get("event"), user=request.user, request=request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self._rows(event))


class AuditViewSet(EventScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = s.AuditSerializer
    scope_module = "audit"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"default": "audit.view"}
    filterset_fields = ["action", "drill", "target_type", "target_id"]
    search_fields = ["message", "actor_repr", "target_repr"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AuditLog.objects.none()
        return AuditLog.objects.filter(event_id=self.get_event().pk)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsSuperuser])
def audit_verify(request):
    r = verify_chain()
    return Response({"ok": r.ok, "checked": r.checked, "first_bad_id": r.first_bad_id, "reason": r.reason})


class TokenViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Your own service tokens. Tokens cannot mint tokens (session login required for create)."""

    serializer_class = s.TokenSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ServiceToken.objects.none()
        return ServiceToken.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        from apps.accounts.twofactor import is_verified

        if getattr(self.request, "service_token", None) is not None:
            raise PermissionDenied("Create tokens from a logged-in session.")
        event = serializer.validated_data.get("event")
        if event is not None and not rbac.has_perm(self.request.user, event, "events.view", request=self.request):
            raise PermissionDenied("You are not a member of this event.")
        tok, raw = ServiceToken.issue(owner=self.request.user, name=serializer.validated_data["name"], event=event,
                                      scopes=serializer.validated_data.get("scopes", []),
                                      expires_at=serializer.validated_data.get("expires_at"),
                                      created_with_2fa=is_verified(self.request))
        log(action="token.created", actor=self.request.user, target=tok, event=event, request=self.request,
            message=f"Service token {tok.name} created", scope={"scopes": tok.scopes})
        tok.token = raw
        serializer.instance = tok

    def perform_destroy(self, instance):
        log(action="token.revoked", actor=self.request.user, target=instance, event=instance.event,
            request=self.request, message=f"Service token {instance.name} revoked")
        instance.delete()


class _VenuePartViewSet(viewsets.ModelViewSet):
    scope_module = "venues"
    venue_field = "venue"

    def get_queryset(self):
        qs = self.model.objects.filter(**{f"{self.venue_field}__in": venue_access.visible(self.request.user,
                                                                                         self.request)})
        venue = self.request.query_params.get("venue")
        return qs.filter(**{f"{self.venue_field}__slug": venue}) if venue else qs

    def _check(self, obj):
        if not venue_access.allowed(self.request.user, obj, "venues.manage", self.request):
            raise PermissionDenied("Missing permission venues.manage for this venue.")

    def perform_create(self, serializer):
        self._check(self.model(**serializer.validated_data) if "zones" not in serializer.validated_data
                    else self.model(**{k: v for k, v in serializer.validated_data.items() if k != "zones"}))
        obj = serializer.save()
        log(action="venue.part_created", actor=self.request.user, target=obj, request=self.request)

    def perform_update(self, serializer):
        self._check(serializer.instance)
        obj = serializer.save()
        self._check(obj)
        log(action="venue.part_updated", actor=self.request.user, target=obj, request=self.request)

    def perform_destroy(self, instance):
        self._check(instance)
        log(action="venue.part_deleted", actor=self.request.user, target=instance, request=self.request)
        instance.delete()


class VenueViewSet(_VenuePartViewSet):
    serializer_class = s.VenueSerializer
    model = Venue
    venue_field = "pk"
    lookup_field = "slug"

    def get_queryset(self):
        return venue_access.visible(self.request.user, self.request)

    def perform_create(self, serializer):
        slug = self.request.data.get("event")
        event = Event.objects.filter(slug=slug).first() if slug else None
        if not self.request.user.is_superuser and (
                event is None or not rbac.has_perm(self.request.user, event, "venues.manage", request=self.request)):
            raise PermissionDenied("Pass 'event' (slug) where you hold venues.manage, or be an instance admin.")
        with transaction.atomic():
            venue = serializer.save()
            if event is not None:
                event.venues.add(venue)
        log(action="venue.created", actor=self.request.user, target=venue, event=event, request=self.request)

    @extend_schema(parameters=[
        OpenApiParameter("step_free", bool, description="Only step-free routes."),
        OpenApiParameter("blocked", str, description="Comma-separated ids of blocked points (e.g. exits).")],
        responses={200: dict})
    @action(detail=True, methods=["get"])
    def routes(self, request, slug=None):
        """The way out from every point: next point, target, distance (m) and the full path (ADR-0026)."""
        venue = self.get_object()
        blocked = [b for b in request.query_params.get("blocked", "").split(",") if b]
        step_free = request.query_params.get("step_free") in ("1", "true", "yes")
        return Response(venue_graph.api_table(venue, blocked=blocked, step_free=step_free))


class BuildingViewSet(_VenuePartViewSet):
    serializer_class = s.BuildingSerializer
    model = Building


class FloorViewSet(_VenuePartViewSet):
    serializer_class = s.FloorSerializer
    model = Floor
    venue_field = "building__venue"


class ZoneViewSet(_VenuePartViewSet):
    serializer_class = s.ZoneSerializer
    model = Zone


class PointViewSet(_VenuePartViewSet):
    serializer_class = s.PointSerializer
    model = Point


class EdgeViewSet(_VenuePartViewSet):
    serializer_class = s.EdgeSerializer
    model = Edge


class RoomViewSet(_VenuePartViewSet):
    serializer_class = s.RoomSerializer
    model = Room


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def extensions_list(request):
    """Extensions and their status (instance level, or ``?event=<slug>``)."""
    event = None
    if request.query_params.get("event"):
        event = get_object_or_404(Event.objects.visible_to(request.user), slug=request.query_params["event"])
        if not rbac.has_perm(request.user, event, "extensions.manage", request=request):
            raise PermissionDenied
    elif not request.user.is_superuser:
        raise PermissionDenied
    return Response([{"key": spec.key, "name": spec.name, "version": spec.version, "scope": spec.scope,
                      "status": ext_services.card_status(spec, event),
                      "features": [f.key for f in spec.features]}
                     for spec in ext_services.specs_for("event" if event else "instance")])


@csrf_exempt
@require_POST
def extension_webhook(request, key, config_id):
    """Inbound webhook: ``POST /api/v1/extensions/<key>/<config-id>/webhook/``.

    The body must be signed with the config's webhook secret (``<signature header>: sha256=<hex HMAC>``).
    Deliveries carrying the same delivery id header are processed once.
    """
    spec = registry.get_extension(key)
    config = ExtensionConfig.objects.filter(pk=config_id, extension=key).select_related("event").first()
    if spec is None or config is None or not spec.inbound_webhooks or spec.handle_webhook is None:
        return JsonResponse({"ok": False, "error": "unknown webhook"}, status=404)
    if not config.enabled:
        return JsonResponse({"ok": False, "error": "extension disabled"}, status=403)
    body = request.body
    if not ext_services.verify_signature(config.webhook_secret, body, request.headers.get(spec.signature_header)):
        ext_services.write_log(config, "warn", "Inbound webhook with invalid signature rejected",
                               ip=request.META.get("REMOTE_ADDR"))
        return JsonResponse({"ok": False, "error": "invalid signature"}, status=401)
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        return JsonResponse({"ok": False, "error": "invalid JSON"}, status=400)
    delivery_id = request.headers.get(spec.delivery_header, "")[:200]
    if not delivery_id and spec.delivery_id is not None:
        delivery_id = (spec.delivery_id(request.headers, body, payload) or "")[:200]
    event_type = request.headers.get(spec.event_header, "")[:100]
    if delivery_id:
        seen = InboundDelivery.objects.filter(config=config, delivery_id=delivery_id).first()
        if seen is not None:
            return JsonResponse({**seen.response, "duplicate": True}, status=seen.status)
    headers = {k: v for k, v in request.headers.items()}
    with transaction.atomic():
        result = spec.handle_webhook(config, headers, body, payload)
        if delivery_id:
            InboundDelivery.objects.create(config=config, delivery_id=delivery_id, event_type=event_type,
                                           status=result.status, response=dict(result.body))
        ext_services.write_log(config, "info" if result.status < 400 else "warn",
                               f"Inbound webhook {event_type or '(no type)'} -> {result.status}")
    return JsonResponse(dict(result.body), status=result.status)
