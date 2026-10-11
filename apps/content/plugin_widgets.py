# SPDX-License-Identifier: AGPL-3.0-or-later
"""Widgets of third-party plugins on screens (ADR-0045).

A plugin registers ``WidgetSpec(key, name, element="evac-x-…", script="<app>/widget.js",
data_sources=(…), settings_schema={…})``. A layout element ``{"type": "plugin", "props": {"widget": key,
"settings": {…}}}`` shows it: the shared renderer loads ``script`` (a JavaScript module from the plugin's static
files) once, creates ``element`` and hands it its settings, the template variables and the payload of the data
sources the widget declared. Screens read those payloads at ``/player/api/content/sources/<key>/``, the editor at
``/e/<event>/content/sources/<key>/``; only data sources declared by a plugin widget are readable this way.
"""
from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.templatetags.static import static

from apps.core import modules
from apps.core.registry import registry

RENDERER = "player/player.js"  # widgets the shared renderer draws itself (text, clock, program, …)


def widgets(event: Any) -> dict[str, dict[str, Any]]:
    """Plugin widgets usable in ``event``: ``{key: {name, element, script, sources, ttl, schema}}``."""
    reg = registry.ensure_loaded()
    out = {}
    for spec in reg.widgets.values():
        if not spec.element or not spec.script or spec.script == RENDERER:
            continue
        if spec.module != "core" and not modules.is_enabled(spec.module, event):
            continue
        ttls = [reg.data_sources[k].ttl_seconds for k in spec.data_sources if k in reg.data_sources]
        out[spec.key] = {"name": spec.name, "element": spec.element, "script": static(spec.script),
                         "sources": list(spec.data_sources), "ttl": max(10, min(ttls)) if ttls else 60,
                         "schema": spec.settings_schema, "description": spec.description}
    return out


def readable_sources(event: Any) -> set[str]:
    return {k for w in widgets(event).values() for k in w["sources"]}


def published_sources(event: Any) -> set[str]:
    """Sources of the plugin widgets that a published layout of ``event`` uses: all a screen may read."""
    cache_key = f"evac:plugin-sources:{event.pk}"
    hit = cache.get(cache_key)
    if hit is not None:
        return set(hit)
    from .models import Layout

    used = set()
    for data in Layout.objects.filter(event=event, published__isnull=False).values_list("published__data", flat=True):
        used |= {str((el.get("props") or {}).get("widget") or "") for el in (data or {}).get("elements") or []
                 if isinstance(el, dict) and el.get("type") == "plugin"}
    all_widgets = widgets(event)
    out = {k for w in used if w in all_widgets for k in all_widgets[w]["sources"]}
    cache.set(cache_key, sorted(out), 30)
    return out


def source_payload(event: Any, key: str, *, screen: bool = False, user: Any = None, request: Any = None) -> Any:
    """The data source's payload for ``event`` (cached for its ``ttl_seconds``). ``KeyError`` if not readable:
    for screens (``screen=True``) only sources of widgets in published layouts; for people (``user``) also the
    source's own permission when it declares one."""
    reg = registry.ensure_loaded()
    spec = reg.data_sources.get(key)
    if spec is None or spec.fetch is None or key not in readable_sources(event):
        raise KeyError(key)
    if screen and key not in published_sources(event):
        raise KeyError(key)
    if user is not None and spec.permission:
        from apps.events import rbac

        if not rbac.has_perm(user, event, spec.permission, request=request):
            raise KeyError(key)
    if spec.module != "core" and not modules.is_enabled(spec.module, event):
        raise KeyError(key)
    cache_key = f"evac:source:{event.pk}:{key}"
    hit = cache.get(cache_key)
    if hit is not None:
        return hit
    data = spec.fetch(event)
    cache.set(cache_key, data, max(5, spec.ttl_seconds))
    return data


def editor_choices(event: Any) -> list[dict[str, Any]]:
    """The editor's list of plugin widgets: what the renderer needs plus the settings schema for the form."""
    return [{"value": k, "label": w["name"], "schema": w["schema"], "description": w["description"],
             "element": w["element"], "script": w["script"], "sources": w["sources"], "ttl": w["ttl"]}
            for k, w in sorted(widgets(event).items(), key=lambda kv: kv[1]["name"])]


def preview_config(event: Any) -> dict[str, Any]:
    """``plugins`` of a preview island's config: the widgets and where the portal serves their data sources."""
    from django.urls import reverse

    return {"widgets": {k: {f: w[f] for f in ("element", "script", "sources", "ttl")}
                        for k, w in widgets(event).items()},
            "sources": reverse("content:sources", args=[event.slug, "x"])[:-2]}
