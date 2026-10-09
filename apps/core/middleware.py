# SPDX-License-Identifier: AGPL-3.0-or-later
"""Core middleware: content security policy, rate limiting, first-run redirect, current event."""
from __future__ import annotations

import secrets

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

from .audit import client_ip


class ContentSecurityPolicyMiddleware(MiddlewareMixin):
    """Strict CSP. ``'nonce'`` in a directive is replaced by the per-request nonce (``request.csp_nonce``).

    Views can widen or replace the policy for their response with ``response.evac_csp = {...}`` (used by
    the sandboxed code mode in Phase 1) or skip it with ``response.evac_csp = None``.
    """

    def process_request(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)

    def process_response(self, request, response):
        if "Content-Security-Policy" in response:
            return response
        policy = getattr(response, "evac_csp", settings.EVAC_CSP)
        if policy is None:
            return response
        nonce = getattr(request, "csp_nonce", "")
        parts = []
        for directive, sources in policy.items():
            values = [f"'nonce-{nonce}'" if s == "'nonce'" else s for s in sources]
            parts.append(f"{directive} {' '.join(values)}".strip())
        response["Content-Security-Policy"] = "; ".join(parts)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(self)")
        return response


def allow_code_frames(response):
    """Pages that render layouts with code elements: scripts carrying the page's nonce may run. The sandboxed
    code frames (``srcdoc``) inherit this policy and add their own, stricter one (ADR-0018)."""
    policy = dict(getattr(response, "evac_csp", settings.EVAC_CSP) or settings.EVAC_CSP)
    policy["script-src"] = [*policy.get("script-src", ["'self'"]), "'nonce'"]
    response.evac_csp = policy
    return response


RATE_LIMITED_PATHS = {
    "/accounts/login/": "login",
    "/accounts/2fa/": "twofactor",
    "/setup/": "setup",
    "/invite/": "invite",
    "/api/v1/extensions/": "webhook",
    "/early-access/": "early_access",
    "/player/api/pair/": "pairing",
}


class RateLimitMiddleware(MiddlewareMixin):
    """Fixed-window per-IP limiter for sensitive endpoints (login, 2FA, setup, inbound webhooks)."""

    def process_request(self, request):
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        for prefix, bucket in RATE_LIMITED_PATHS.items():
            if request.path.startswith(prefix):
                limit = settings.EVAC_RATE_LIMITS.get(bucket, 60)
                key = f"rl:{bucket}:{client_ip(request)}"
                try:
                    cache.add(key, 0, 60)
                    count = cache.incr(key)
                except Exception:  # noqa: BLE001 - cache unavailable: fail open, other controls remain
                    return None
                if count > limit:
                    return HttpResponse("Too many requests", status=429, content_type="text/plain")
        return None


FIRST_RUN_EXEMPT = ("/setup/", "/early-access/", "/static/", "/media/", "/healthz", "/readyz", "/metrics",
                    "/manifest.webmanifest", "/sw.js", "/offline/",
                    "/api/schema/", "/favicon.ico", "/docs/", "/player/")


class FirstRunMiddleware(MiddlewareMixin):
    """Until the first account exists every page redirects to the first-run wizard (``/setup/``)."""

    CACHE_KEY = "evac:has-users"

    def process_request(self, request):
        if request.path.startswith(FIRST_RUN_EXEMPT):
            return None
        if cache.get(self.CACHE_KEY):
            return None
        from django.contrib.auth import get_user_model

        if get_user_model().objects.exists():
            cache.set(self.CACHE_KEY, True, 300)
            return None
        if request.path.startswith("/api/"):
            return HttpResponse('{"detail": "EVAC is not set up yet; open /setup/ in a browser."}', status=503,
                                content_type="application/json")
        return redirect("portal:setup")


class CurrentEventMiddleware(MiddlewareMixin):
    """Resolves the event from ``/e/<slug>/...`` URLs (or the session) onto ``request.event``."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        request.event = None
        slug = view_kwargs.get("slug") if request.path.startswith("/e/") else None
        if not slug and hasattr(request, "session"):
            slug = request.session.get("current_event")
        if slug:
            from apps.events.models import Event

            request.event = Event.objects.filter(slug=slug).first()
        return None
