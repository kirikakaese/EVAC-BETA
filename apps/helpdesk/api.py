# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API of the helpdesk: ``/api/v1/events/<slug>/helpdesk-requests/``, ``…/lost-found/`` and ``…/faq/``."""
from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.core import modules

from .models import FaqEntry, LostFound, Ticket

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ["id", "reference", "subject", "body", "category", "name", "contact", "status", "assignee",
                  "source", "created_at", "updated_at"]
        read_only_fields = fields


class LostFoundSerializer(serializers.ModelSerializer):
    class Meta:
        model = LostFound
        fields = ["id", "reference", "kind", "what", "category", "colour", "description", "where", "room", "when",
                  "storage", "name", "contact", "status", "match", "handed_to", "handed_at", "public", "source",
                  "created_at"]
        read_only_fields = fields


class FaqSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaqEntry
        fields = ["id", "question", "answer", "topic", "order", "public", "on_screens"]
        read_only_fields = fields


class _HelpdeskMixin(EventScopedMixin):
    scope_module = "helpdesk"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "helpdesk.view", "HEAD": "helpdesk.view", "OPTIONS": "helpdesk.view",
                         "default": "helpdesk.manage"}
    model: Any = None

    def get_event(self) -> Any:
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("helpdesk", event):
            raise NotFound("The helpdesk module is switched off for this event.")
        return event

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return self.model.objects.none()
        return self.model.objects.filter(event=self.get_event())


@EVENT_SLUG
class TicketViewSet(_HelpdeskMixin, viewsets.ReadOnlyModelViewSet):
    """Requests (``?status=new``)."""

    serializer_class = TicketSerializer
    model = Ticket
    filterset_fields = ["status", "category"]


@EVENT_SLUG
class LostFoundViewSet(_HelpdeskMixin, viewsets.ReadOnlyModelViewSet):
    """Lost reports and found items (``?kind=found&status=open``)."""

    serializer_class = LostFoundSerializer
    model = LostFound
    filterset_fields = ["kind", "status", "category"]
    search_fields = ["what", "description", "colour", "reference"]


@EVENT_SLUG
class FaqViewSet(_HelpdeskMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = FaqSerializer
    model = FaqEntry


ROUTES = [(r"events/(?P<event_slug>[^/.]+)/helpdesk-requests", TicketViewSet, "event-helpdesk-request"),
          (r"events/(?P<event_slug>[^/.]+)/lost-found", LostFoundViewSet, "event-lost-found"),
          (r"events/(?P<event_slug>[^/.]+)/faq", FaqViewSet, "event-faq")]
