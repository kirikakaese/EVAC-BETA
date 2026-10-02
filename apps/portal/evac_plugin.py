# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import NavEntry, PluginManifest
from apps.core.registry import Registry

manifest = PluginManifest(key="portal", name="Portal", version="0.1.0", kind="core")


def register(r: Registry) -> None:
    for order, label, url, active in [
        (20, _("Modules"), "portal:instance_modules", ("portal:instance_modules",)),
        (25, _("Settings"), "portal:instance_settings", ("portal:instance_settings*",)),
        (40, _("Audit log"), "portal:instance_audit", ("portal:instance_audit",)),
        (5, _("Events"), "portal:home", ("portal:home", "portal:event_create", "portal:event_import")),
    ]:
        r.nav(NavEntry(module="core", label=str(label), url_name=url, permission="admin", section="admin",
                       order=order, global_=True, active=active))
