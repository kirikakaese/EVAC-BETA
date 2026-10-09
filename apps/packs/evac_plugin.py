# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ModuleSpec, NavEntry, PermissionSpec, PluginManifest, SettingsNamespace
from apps.core.registry import Registry

manifest = PluginManifest(key="packs", name="Screen packs", version="0.1.0", kind="module")


def register(r: Registry) -> None:
    r.module(ModuleSpec(key="packs", name=str(_("Screen packs")), order=37, category="screens",
                        depends_on=("content",),
                        description=str(_("Export and import layouts, themes, files, widgets and playlists as "
                                          "signed .evacpack files, and start from built-in packs."))))
    r.permissions_([
        PermissionSpec("packs.export", str(_("Export screen packs"))),
        PermissionSpec("packs.import", str(_("Import screen packs (also from a URL and the gallery)"))),
    ])
    r.nav(NavEntry(module="packs", label=str(_("Screen packs")), url_name="packs:index",
                   permission="packs.import", section="content", order=27))
    r.nav(NavEntry(module="packs", label=str(_("Pack keys")), url_name="packs_admin:keys", permission="admin",
                   section="admin", order=45, global_=True))
    r.settings_namespace(SettingsNamespace(
        key="packs", title=str(_("Screen packs")), module="packs", levels=("instance",), order=37,
        schema={"type": "object", "properties": {
            "signer_name": {"type": "string", "title": "Signer name", "default": "EVAC", "maxLength": 200,
                            "description": "Shown to people who import packs exported here."},
            "require_trusted": {"type": "boolean", "title": "Only import packs signed by a trusted key",
                                "default": False,
                                "description": "Unsigned packs and packs from unknown keys are refused (built-in "
                                               "packs are always allowed)."},
            "allow_url_import": {"type": "boolean", "title": "Allow importing packs from a URL", "default": True},
            "allow_private_networks": {"type": "boolean", "title": "Allow pack URLs in private networks",
                                       "default": False},
            "max_size_mb": {"type": "integer", "title": "Largest pack (MB)", "default": 200, "minimum": 1,
                            "maximum": 4000},
        }}))
