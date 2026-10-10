# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.core.registry import registry

from . import views

app_name = "api"

router = DefaultRouter()
router.register("events", views.EventViewSet, basename="event")
router.register("venues", views.VenueViewSet, basename="venue")
router.register("buildings", views.BuildingViewSet, basename="building")
router.register("floors", views.FloorViewSet, basename="floor")
router.register("zones", views.ZoneViewSet, basename="zone")
router.register("rooms", views.RoomViewSet, basename="room")
router.register("points", views.PointViewSet, basename="point")
router.register("edges", views.EdgeViewSet, basename="edge")
router.register("tokens", views.TokenViewSet, basename="token")
for prefix, viewset, basename in registry.ensure_loaded().api_routes:
    router.register(prefix, viewset, basename=basename)

event_router = DefaultRouter()
event_router.include_root_view = False
event_router.register("roles", views.RoleViewSet, basename="event-role")
event_router.register("members", views.MemberViewSet, basename="event-member")
event_router.register("modules", views.ModuleViewSet, basename="event-module")
event_router.register("audit", views.AuditViewSet, basename="event-audit")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("me/", views.me, name="me"),
    path("registry/", views.registry_view, name="registry"),
    path("audit/verify/", views.audit_verify, name="audit-verify"),
    path("extensions/", views.extensions_list, name="extensions"),
    path("extensions/<slug:key>/<uuid:config_id>/webhook/", views.extension_webhook, name="extension-webhook"),
    path("events/<slug:event_slug>/", include(event_router.urls)),
    path("", include(router.urls)),
]
