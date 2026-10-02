# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ModuleSpec, NavEntry, PermissionSpec, PluginManifest
from apps.core.registry import Registry

manifest = PluginManifest(key="extensions", name="Extensions framework", version="0.1.0", kind="core")


def register(r: Registry) -> None:
    r.module(ModuleSpec(key="extensions", name=str(_("Extensions")), order=5, category="integration",
                        description=str(_("Integrations with external systems (DIAL, pretalx, Matrix, webhooks, "
                                          "...), configured under Settings -> Extensions."))))
    r.permission(PermissionSpec("extensions.manage", str(_("Configure extensions and their credentials"))))
    r.nav(NavEntry(module="extensions", label=str(_("Extensions")), url_name="extensions:instance_index",
                   permission="admin", section="admin", order=30, global_=True, active=("extensions:instance_*",)))
