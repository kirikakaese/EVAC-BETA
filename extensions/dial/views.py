# SPDX-License-Identifier: AGPL-3.0-or-later
"""DIAL pages of an event (``/e/<slug>/dial/``): link status, DECT, broadcasts, phone recordings, widgets, roles."""
from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.audit import log
from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import link, outbound, presets, roles, sources
from .client import DialError
from .models import Broadcast, DectAlert, Recording, RoleMapping
from .ops import PERM_STATUS

MANAGE = "extensions.manage"


def _config(event: Any) -> Any:
    from apps.extensions import services as ext

    return ext.effective(link.KEY, event)


def _settings_url(event: Any) -> str:
    return reverse("extensions:event_detail", args=[event.slug, link.KEY])


@event_view(PERM_STATUS, module="extensions")
def status(request, slug, *, event):
    config = _config(event)
    ctx: dict[str, Any] = {"event": event, "config": config, "settings_url": _settings_url(event),
                           "can_manage": rbac.has_any(request.user, event, MANAGE, request=request),
                           "can_roles": rbac.has_any(request.user, event, "events.roles", request=request)}
    if config is not None:
        ctx["webhook_url"] = request.build_absolute_uri(
            reverse("api:extension-webhook", args=[link.KEY, config.pk]))
        ctx["dial_webhooks_url"] = f"{(config.settings.get('base_url') or '').rstrip('/')}/e/" \
                                   f"{config.settings.get('event', '')}/orga/webhooks/"
        ctx["broadcasts"] = Broadcast.objects.filter(config=config)[:20]
        ctx["recordings"] = Recording.objects.filter(config=config).select_related("announcement")[:10]
        ctx["alerts"] = DectAlert.objects.filter(config=config)[:10]
        ctx["features"] = [(f, config.feature_enabled(f.key)) for f in config.spec.features]
        ctx["scopes"] = link.SCOPES
        if config.feature_enabled("data_sources"):
            ctx["dect"] = sources.snapshot(config, "dect")
    return render(request, "dial/status.html", ctx)


@require_POST
@event_view(MANAGE, module="extensions")
def test_broadcast(request, slug, *, event):
    config = _config(event)
    if config is None:
        return redirect(_settings_url(event))
    kind = request.POST.get("kind")
    text = (request.POST.get("text") or "").strip()[:480]
    if kind not in (Broadcast.Kind.EMERGENCY, Broadcast.Kind.MESSAGE) or not text:
        messages.error(request, _("Choose what to send and write a text."))
        return redirect("dial:status", event.slug)
    b = outbound.queue(config, kind=kind, source=Broadcast.Source.TEST, text=text,
                       group=str(link.settings_of(config).get("broadcast_group") or ""))
    log(action="dial.test_broadcast", actor=request.user, event=event, request=request, target=b,
        message=f"DIAL test {kind}: {text}")
    messages.success(request, _("Queued. The result appears under Broadcasts."))
    return redirect("dial:status", event.slug)


@require_POST
@event_view(MANAGE, module="extensions")
def install_widgets(request, slug, *, event):
    from apps.core import modules

    if _config(event) is None or not modules.is_enabled("widgets", event):
        messages.error(request, _("Link DIAL and switch the widgets module on first."))
        return redirect("dial:status", event.slug)
    try:
        made = presets.install(event, actor=request.user, request=request)
    except (ValidationError, DialError) as exc:
        messages.error(request, str(exc))
        return redirect("dial:status", event.slug)
    messages.success(request, _("%(n)s widgets added (Widgets → Custom widgets).") % {"n": len(made)})
    return redirect("dial:status", event.slug)


@event_view("events.roles", module="extensions")
def role_mapping(request, slug, *, event):
    config = _config(event)
    if config is None:
        return redirect(_settings_url(event))
    can_assign = rbac.has_any(request.user, event, "events.members", request=request)
    form = roles.MappingForm(request.POST if request.POST.get("what") == "mapping" else None, config=config)
    if form.is_bound and form.is_valid():
        roles.save_mapping(config, form.cleaned_data, actor=request.user, request=request)
        messages.success(request, _("Mapping saved."))
        return redirect("dial:roles", event.slug)
    snap = sources.snapshot(config, "members")
    proposals = roles.proposals(config, snap.data.get("items") or []) if snap is not None else []
    if request.POST.get("what") == "assign":
        if not can_assign:
            raise PermissionDenied("events.members")
        n = roles.apply(config, proposals, request.POST, actor=request.user, request=request)
        messages.success(request, _("%(n)s roles assigned.") % {"n": n})
        return redirect("dial:roles", event.slug)
    return render(request, "dial/roles.html", {
        "event": event, "config": config, "form": form, "proposals": proposals, "snapshot": snap,
        "can_assign": can_assign, "mappings": RoleMapping.objects.filter(config=config).select_related("role"),
        "members": roles.member_choices(event)})
