# SPDX-License-Identifier: AGPL-3.0-or-later
"""Template context shared by every page: navigation, current event, permissions, asset version."""
from __future__ import annotations

import fnmatch
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from . import modules
from .notify import unread_count
from .registry import registry

VERSIONED_ASSETS = ("css/evac.css", "js/evac.js", "js/webauthn.js", "vendor/htmx.min.js", "js/staff-sw.js",
                    "js/scanner.js")


@lru_cache(maxsize=1)
def asset_version() -> str:
    import hashlib

    h = hashlib.sha256()
    for rel in VERSIONED_ASSETS:
        p = Path(settings.BASE_DIR) / "static" / rel
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


def _nav(request, event, perms):
    match = getattr(request, "resolver_match", None)
    current = f"{match.namespace}:{match.url_name}" if match and match.namespace else (match.url_name if match else "")
    sections: dict[str, list[dict]] = {}
    user = request.user
    for entry in registry.nav_for():
        if entry.global_:
            if entry.permission == "admin" and not user.is_superuser:
                continue
            if not user.is_authenticated:
                continue
            args: list = []
        else:
            if event is None or not modules.is_enabled(entry.module, event):
                continue
            if entry.permission and entry.permission not in perms:
                continue
            args = [event.slug]
        try:
            url = reverse(entry.url_name, args=args)
        except NoReverseMatch:
            continue
        patterns = entry.active or (entry.url_name.split(":")[0] + ":*",)
        sections.setdefault(entry.section, []).append({
            "label": entry.label, "url": url, "icon": entry.icon,
            "active": any(fnmatch.fnmatchcase(current, p) for p in patterns),
        })
    return sections


SECTION_TITLES = {"event": "Event", "operations": "Operations", "content": "Content", "settings": "Settings",
                  "admin": "Instance"}


def _ws_base(request) -> str:
    base = settings.EVAC_REALTIME_URL
    if not base:
        return f"{'wss' if request.is_secure() else 'ws'}://{request.get_host()}"
    return base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)


def evac(request):
    from apps.events import rbac

    event = getattr(request, "event", None)
    user = getattr(request, "user", None)
    perms: set[str] = set()
    blocked: list = []
    if event is not None and user is not None and user.is_authenticated:
        info = rbac.effective(user, event, request=request)
        if not info.member and not user.is_superuser:
            event = None
        else:
            perms, blocked = info.permissions, info.blocked_roles
    nav = _nav(request, event, perms) if user is not None else {}
    switcher = []
    if user is not None and user.is_authenticated:
        from apps.events.models import Event

        switcher = list(Event.objects.visible_to(user).exclude(state="archived").only("slug", "name")[:50])
    return {
        "current_event": event,
        "event_perms": perms,
        "switcher_events": switcher,
        "blocked_roles": blocked,
        "nav_sections": [(SECTION_TITLES.get(k, k.title()), v) for k, v in
                         sorted(nav.items(), key=lambda kv: list(SECTION_TITLES).index(kv[0])
                                if kv[0] in SECTION_TITLES else 99)],
        "ASSET_VERSION": asset_version(),
        "EVAC_MODE": settings.EVAC_MODE,
        "EVAC_VERSION": __import__("evac").__version__,
        "unread_notifications": unread_count(user) if user is not None else 0,
        "csp_nonce": getattr(request, "csp_nonce", ""),
        "realtime_ws_base": _ws_base(request),
    }
