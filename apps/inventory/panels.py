# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inventory in the control room and on the staff page."""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.events import rbac

from . import services
from .models import Loan


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "inventory.view", request=request):
        return None
    loans = list(services.open_loans(event)[:200])
    now = timezone.now()
    overdue = [ln for ln in loans if ln.due_at and ln.due_at < now]
    return {"out": len(loans), "overdue": overdue[:8], "now": now}


def staff_card(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "inventory.view", request=request):
        return None
    mine = list(Loan.objects.filter(item__event=event, borrower_user=request.user, returned_at__isnull=True)
                .select_related("item"))
    return {"mine": mine, "can_lend": rbac.has_any(request.user, event, "inventory.lend", request=request),
            "now": timezone.now()}
