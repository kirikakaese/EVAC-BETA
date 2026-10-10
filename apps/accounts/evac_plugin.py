# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import NavEntry, PluginManifest
from apps.core.registry import Registry

manifest = PluginManifest(key="accounts", name="Accounts", version="0.1.0", kind="core")


def register(r: Registry) -> None:
    from . import sync

    r.sync(sync.spec())
    r.nav(NavEntry(module="core", label=str(_("Users")), url_name="portal:users", permission="admin",
                   section="admin", order=10, global_=True, active=("portal:user*",)))
