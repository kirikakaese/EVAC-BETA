# SPDX-License-Identifier: AGPL-3.0-or-later
"""Early-access gate: one shared password in front of the whole instance (ADR-0012).

Active when ``EVAC_EARLY_ACCESS_PASSWORD`` is set. Visitors without a valid gate cookie are sent to
``/early-access/`` (HTML) or get ``401`` (API). The cookie is signed with ``SECRET_KEY`` and bound to a
fingerprint of the current password, so changing the password invalidates every cookie.

Not gated: static files, health/readiness/metrics probes, signed inbound webhooks and requests carrying an
EVAC service token (``Authorization: Bearer evac_…``) - those are authenticated by their own secret.
The gate is an access *barrier*, not an account system: users still log in normally behind it.
"""
from __future__ import annotations

import logging
import re

from django.conf import settings
from django.core import signing
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

seclog = logging.getLogger("evac.security")

COOKIE = "evac_early_access"
SALT = "evac.early_access"
#: screens (``/player/`` and its WebSocket) authenticate with device tokens and cannot type the password
EXEMPT_PREFIXES = ("/early-access/", "/static/", "/healthz", "/readyz", "/metrics", "/favicon.ico", "/player/",
                   "/bridge/", "/evac/", "/api/v1/node/")
WS_EXEMPT_PATHS = ("/ws/screen/",)
WEBHOOK_PATH = re.compile(r"^/api/v1/extensions/[\w-]+/[0-9a-f-]{36}/webhook/$")


def password() -> str:
    return getattr(settings, "EVAC_EARLY_ACCESS_PASSWORD", "") or ""


def enabled() -> bool:
    return bool(password())


def _fingerprint() -> str:
    return salted_hmac(SALT, password()).hexdigest()[:24]


def make_cookie_value() -> str:
    return signing.dumps({"fp": _fingerprint()}, salt=SALT, compress=True)


def cookie_valid(value: str | None) -> bool:
    if not value:
        return False
    max_age = int(getattr(settings, "EVAC_EARLY_ACCESS_DAYS", 30)) * 86400
    try:
        data = signing.loads(value, salt=SALT, max_age=max_age)
    except signing.BadSignature:
        return False
    return isinstance(data, dict) and constant_time_compare(str(data.get("fp", "")), _fingerprint())


def exempt(request) -> bool:
    path = request.path
    if path.startswith(EXEMPT_PREFIXES) or WEBHOOK_PATH.match(path):
        return True
    auth = request.headers.get("Authorization", "")
    return auth.split(" ", 1)[-1].startswith("evac_") and auth.lower().startswith(("bearer ", "token "))


def granted(request) -> bool:
    return not enabled() or cookie_valid(request.COOKIES.get(COOKIE))


class EarlyAccessMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if granted(request) or exempt(request):
            return None
        if request.path.startswith("/api/"):
            return JsonResponse({"detail": "This EVAC instance is in early access. Unlock it in a browser first, "
                                           "or use a service token."}, status=401)
        return redirect(f"{reverse('early_access')}?next={request.get_full_path()}")


def _safe_next(request, url: str) -> str:
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return url
    return "/"


@require_http_methods(["GET", "POST"])
def gate(request):
    next_url = _safe_next(request, request.POST.get("next") or request.GET.get("next") or "/")
    if not enabled() or granted(request):
        return redirect(next_url)
    error = False
    if request.method == "POST":
        if constant_time_compare(request.POST.get("password", ""), password()):
            resp = redirect(next_url)
            resp.set_cookie(COOKIE, make_cookie_value(), max_age=int(settings.EVAC_EARLY_ACCESS_DAYS) * 86400,
                            httponly=True, samesite="Lax",
                            secure=request.is_secure() or bool(getattr(settings, "SESSION_COOKIE_SECURE", False)))
            seclog.info("early access granted ip=%s", request.META.get("REMOTE_ADDR"))
            return resp
        error = True
        seclog.info("early access password wrong ip=%s", request.META.get("REMOTE_ADDR"))
    return render(request, "core/early_access.html", {
        "next": next_url, "error": error, "message": getattr(settings, "EVAC_EARLY_ACCESS_MESSAGE", ""),
    }, status=401 if error else 200)


class EarlyAccessASGIMiddleware:
    """WebSockets bypass Django's middleware stack; apply the same gate to them."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket" and enabled() and scope.get("path") not in WS_EXEMPT_PATHS:
            from http.cookies import SimpleCookie

            raw = b"; ".join(v for k, v in scope.get("headers", []) if k == b"cookie").decode("latin-1")
            jar = SimpleCookie()
            jar.load(raw)
            value = jar[COOKIE].value if COOKIE in jar else None
            if not cookie_valid(value):
                await send({"type": "websocket.close", "code": 4401})
                return
        await self.app(scope, receive, send)
