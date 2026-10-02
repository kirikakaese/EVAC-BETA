# SPDX-License-Identifier: AGPL-3.0-or-later
"""Root URL configuration.

Module UIs: an installed app with ``urls.py`` declaring ``PORTAL_MOUNT = True`` is mounted at
``/e/<slug>/<app label>/`` under its own namespace (same convention as PET).
"""
from importlib import import_module

from django.apps import apps as django_apps
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerSplitView

# Swagger UI / ReDoc load their bundles from a CDN (online only; the schema itself at /api/schema/ works
# offline). Their responses get a CSP that allows exactly that CDN.
DOCS_CSP = {
    "default-src": ["'self'"], "script-src": ["'self'", "https://cdn.jsdelivr.net"],
    "style-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://fonts.googleapis.com"],
    "img-src": ["'self'", "data:", "https://cdn.jsdelivr.net", "https://cdn.redoc.ly"],
    "font-src": ["'self'", "https://fonts.gstatic.com"], "worker-src": ["'self'", "blob:"],
    "connect-src": ["'self'"], "frame-ancestors": ["'none'"],
}


class _CdnCsp:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response.evac_csp = DOCS_CSP
        return response


class SwaggerView(_CdnCsp, SpectacularSwaggerSplitView):
    pass


class RedocView(_CdnCsp, SpectacularRedocView):
    pass


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("api/v1/", include("apps.api.urls", namespace="api")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", RedocView.as_view(url_name="schema"), name="redoc"),
    path("", include("apps.extensions.urls", namespace="extensions")),
]

for _cfg in django_apps.get_app_configs():
    if _cfg.label in ("portal", "api", "accounts", "core", "extensions"):
        continue
    try:
        _mod = import_module(f"{_cfg.name}.urls")
    except ModuleNotFoundError as exc:
        if exc.name != f"{_cfg.name}.urls":
            raise
        continue
    if getattr(_mod, "PORTAL_MOUNT", False):
        urlpatterns.append(path(f"e/<slug:slug>/{_cfg.label}/", include(f"{_cfg.name}.urls", namespace=_cfg.label)))

urlpatterns += [
    path("", include("apps.core.urls", namespace="core")),
    path("", include("apps.portal.urls", namespace="portal")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
