# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pages for venue nodes (ADR-0036): the instance's node list, and per event the checkout to a node."""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.events import rbac
from apps.portal.shortcuts import event_view, superuser_view

from . import central
from .models import Checkout, Node, NodeEvent, NodeIdentity, ProxiedAction, ReceivedOp

PERM = "nodes.checkout"


def _uuid(value: Any) -> str | None:
    import uuid

    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        return None


@superuser_view
def nodes_page(request: HttpRequest) -> HttpResponse:
    code = ""
    code_for: Node | None = None
    if request.method == "POST":
        what = request.POST.get("what")
        if what == "add":
            name = request.POST.get("name", "").strip()
            if not name:
                messages.error(request, _("Give the node a name."))
                return redirect("nodes_admin:index")
            code_for, code = central.register(name, actor=request.user, request=request)
        else:
            node = get_object_or_404(Node, pk=_uuid(request.POST.get("pk")) or "00000000-0000-0000-0000-000000000000")
            if what == "code":
                code_for, code = node, central.new_code(node, actor=request.user, request=request)
            elif what == "revoke":
                try:
                    central.revoke(node, actor=request.user, request=request)
                    messages.success(request, _("Node revoked."))
                except central.SyncError as err:
                    messages.error(request, str(err))
                return redirect("nodes_admin:index")
    nodes = Node.objects.all()
    open_by_node: dict[Any, list[Checkout]] = {}
    for co in central.open_checkouts():
        open_by_node.setdefault(co.node_id, []).append(co)
    return render(request, "nodes/nodes.html", {
        "rows": [{"node": n, "checkouts": open_by_node.get(n.pk, [])} for n in nodes], "code": code,
        "code_for": code_for, "central_url": request.build_absolute_uri("/"), "mode": settings.EVAC_MODE,
        "identity": NodeIdentity.objects.filter(pk=1).first(), "held": NodeEvent.objects.all()})


@event_view("events.view")
def event_node(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    can = rbac.has_perm(request.user, event, PERM, request=request)
    co = central.checkout_of(event)
    if request.method == "POST":
        if not can:
            raise PermissionDenied
        what = request.POST.get("what")
        try:
            if what == "checkout":
                pk = _uuid(request.POST.get("node"))
                node = Node.objects.filter(pk=pk, revoked_at__isnull=True).first() if pk else None
                if node is None:
                    raise central.SyncError(_("Choose a node."))
                central.checkout(event, node, actor=request.user, request=request)
                messages.success(request, _("Checked out to %(n)s. It takes over at its next sync.") % {"n": node})
            elif what == "checkin" and co is not None:
                central.request_checkin(co, actor=request.user, request=request)
                messages.success(request, _("Check-in requested. The node sends what is pending and hands back."))
            elif what == "force" and co is not None:
                central.force_checkin(co, actor=request.user, request=request,
                                      reason=request.POST.get("reason", "")[:200])
                messages.warning(request, _("Taken back from the node at the last synced position."))
        except central.SyncError as err:
            messages.error(request, str(err))
        return redirect("nodes:index", event.slug)
    history = Checkout.objects.filter(event=event).select_related("node")[:10]
    return render(request, "nodes/event.html", {
        "event": event, "co": co, "can": can, "history": history,
        "nodes": Node.objects.filter(enrolled_at__isnull=False, revoked_at__isnull=True),
        "actions": ProxiedAction.objects.filter(checkout=co).order_by("-id")[:10] if co else [],
        "ops": ReceivedOp.objects.filter(checkout__event=event).count(), "mode": settings.EVAC_MODE,
        "held": NodeEvent.objects.filter(pk=event.pk).first()})
