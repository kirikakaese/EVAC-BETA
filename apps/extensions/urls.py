# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instance-level pages at /settings/extensions/, event-level at /e/<slug>/settings/extensions/.

Extensions with custom views (``ExtensionSpec.urls``) are mounted below their settings page at
``.../<key>/x/``; those views receive ``key`` and (event level) ``slug``.
"""
from django.urls import include, path

from apps.core.registry import registry

from . import views

app_name = "extensions"


def _patterns(prefix: str, name_prefix: str):
    out = [
        path(f"{prefix}", views.index, name=f"{name_prefix}_index"),
        path(f"{prefix}<slug:key>/", views.detail, name=f"{name_prefix}_detail"),
        path(f"{prefix}<slug:key>/test/", views.test, name=f"{name_prefix}_test"),
        path(f"{prefix}<slug:key>/webhook-secret/", views.webhook_secret, name=f"{name_prefix}_webhook_secret"),
        path(f"{prefix}<slug:key>/disconnect/", views.disconnect, name=f"{name_prefix}_disconnect"),
    ]
    for spec in registry.ensure_loaded().extensions.values():
        if spec.urls:
            # the key is literal: every extension gets its own mount (``<slug:key>`` would send all to the first)
            out.append(path(f"{prefix}{spec.key}/x/", include((spec.urls, spec.key),
                                                              namespace=f"{name_prefix}_{spec.key}"),
                            {"key": spec.key}))
    return out


urlpatterns = _patterns("settings/extensions/", "instance") + _patterns("e/<slug:slug>/settings/extensions/", "event")
