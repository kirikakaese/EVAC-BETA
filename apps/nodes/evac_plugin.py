# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venue nodes (ADR-0002, ADR-0036): part of the core, always on."""
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import NavEntry, PermissionSpec, PluginManifest
from apps.core.registry import Registry

manifest = PluginManifest(key="nodes", name="Venue nodes", version="1.0.0", kind="core")


def register(r: Registry) -> None:
    r.permission(PermissionSpec("nodes.checkout", str(_("Hand the event to a venue node and take it back")),
                                sensitive=True))
    r.nav(NavEntry(module="core", label=str(_("Venue nodes")), url_name="nodes_admin:index", permission="admin",
                   section="admin", order=35, global_=True, active=("nodes_admin:*",)))
    r.nav(NavEntry(module="core", label=str(_("Venue node")), url_name="nodes:index", permission="nodes.checkout",
                   section="settings", order=80, active=("nodes:*",)))
