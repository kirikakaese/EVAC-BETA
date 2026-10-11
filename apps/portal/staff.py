# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staff PWA (ADR-0010, ADR-0021): web app manifest, service worker, offline page and the staff page.

The staff page is a phone-first page of cards; modules contribute cards with ``r.staff_card`` (announcements:
approvals and quick send). It shows alerts full-screen with sound, enables Web Push on the device and queues
actions taken offline (``data-offline`` forms in evac.js)."""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_control

from apps.core import modules, webpush
from apps.core.context_processors import asset_version
from apps.core.models import Notification, PushSubscription
from apps.core.registry import registry

from .shortcuts import event_view


@cache_control(max_age=3600)
def manifest(request):
    data = {
        "name": "EVAC",
        "short_name": "EVAC",
        "description": str(_("Event and venue operations for staff: alerts, announcements, approvals.")),
        "start_url": reverse("portal:staff_start"),
        "scope": "/",
        "display": "standalone",
        "background_color": "#0d1117",
        "theme_color": "#15803d",
        "icons": [
            {"src": static("icons/evac-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": static("icons/evac-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            {"src": static("icons/favicon.svg"), "sizes": "any", "type": "image/svg+xml"},
        ],
    }
    return HttpResponse(json.dumps(data), content_type="application/manifest+json")


SHELL_ASSETS = ("css/evac.css", "js/evac.js", "js/scanner.js", "vendor/htmx.min.js", "icons/evac-192.png",
                "icons/favicon.svg")


@cache_control(no_cache=True)
def service_worker(request):
    version = asset_version()
    shell = ["/offline/"] + [f"{static(p)}?v={version}" for p in SHELL_ASSETS]
    source = (Path(settings.BASE_DIR) / "static" / "js" / "staff-sw.js").read_text()
    source = source.replace("__VERSION__", version).replace("__SHELL__", json.dumps(shell))
    response = HttpResponse(source, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


def offline(request):
    return render(request, "portal/offline.html", {})


def staff_start(request):
    """PWA start URL: the staff page of the current event, else the home page."""
    from django.shortcuts import redirect

    slug = request.session.get("current_event") if hasattr(request, "session") else None
    if request.user.is_authenticated and slug:
        return redirect("portal:staff", slug)
    return redirect("portal:home")


@event_view("events.view")
def staff(request, slug, *, event):
    cards = []
    for spec in sorted(registry.ensure_loaded().staff_cards.values(), key=lambda s: (s.order, s.key)):
        if spec.module != "core" and not modules.is_enabled(spec.module, event):
            continue
        ctx = spec.context(request, event)
        if ctx is not None:
            cards.append({"spec": spec, "ctx": {**ctx, "event": event, "request": request}})
    return render(request, "portal/staff.html", {
        "event": event, "cards": cards,
        "notifications": Notification.objects.filter(user=request.user).order_by("-created_at")[:8],
        "devices": PushSubscription.objects.filter(user=request.user).count(),
        "vapid_key": webpush.public_key(),
    })

