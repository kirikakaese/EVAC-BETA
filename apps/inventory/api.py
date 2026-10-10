# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST API of inventory: ``/api/v1/events/<slug>/inventory-items/`` (with the open loan) and ``…/loans/``
(``?open=1``)."""
from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated

from apps.api.permissions import EventPermission, HasScope
from apps.api.views import EventScopedMixin
from apps.core import modules

from .models import Item, Loan

EVENT_SLUG = extend_schema(parameters=[OpenApiParameter("event_slug", str, OpenApiParameter.PATH)])


class InventoryLoanSerializer(serializers.ModelSerializer):
    asset_tag = serializers.CharField(source="item.asset_tag", read_only=True)

    class Meta:
        model = Loan
        fields = ["id", "item", "asset_tag", "borrower", "contact", "lent_at", "due_at", "returned_at", "condition"]
        read_only_fields = fields


class InventoryItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    loan = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = ["id", "asset_tag", "name", "category", "category_name", "serial", "status", "room", "location",
                  "loan"]
        read_only_fields = fields

    def get_loan(self, obj: Item) -> dict[str, Any] | None:
        loan = obj.loans.filter(returned_at__isnull=True).first()
        return InventoryLoanSerializer(loan).data if loan else None


class _InventoryMixin(EventScopedMixin):
    scope_module = "inventory"
    permission_classes = [IsAuthenticated, HasScope, EventPermission]
    event_permissions = {"GET": "inventory.view", "HEAD": "inventory.view", "OPTIONS": "inventory.view",
                         "default": "inventory.manage"}

    def get_event(self) -> Any:
        event = super().get_event()
        if not getattr(self, "swagger_fake_view", False) and not modules.is_enabled("inventory", event):
            raise NotFound("The inventory module is switched off for this event.")
        return event


@EVENT_SLUG
class ItemViewSet(_InventoryMixin, viewsets.ReadOnlyModelViewSet):
    """Items with their asset tag, status and the open loan (who has it)."""

    serializer_class = InventoryItemSerializer
    filterset_fields = ["status", "category"]
    search_fields = ["name", "asset_tag", "serial"]

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return Item.objects.none()
        return Item.objects.filter(event=self.get_event()).select_related("category")


@EVENT_SLUG
class LoanViewSet(_InventoryMixin, viewsets.ReadOnlyModelViewSet):
    """Loans, newest first (``?open=1``: only items still out)."""

    serializer_class = InventoryLoanSerializer

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return Loan.objects.none()
        qs = Loan.objects.filter(item__event=self.get_event()).select_related("item")
        if self.request.query_params.get("open") in ("1", "true"):
            qs = qs.filter(returned_at__isnull=True)
        return qs


ROUTES = [(r"events/(?P<event_slug>[^/.]+)/inventory-items", ItemViewSet, "event-inventory-item"),
          (r"events/(?P<event_slug>[^/.]+)/loans", LoanViewSet, "event-loan")]
