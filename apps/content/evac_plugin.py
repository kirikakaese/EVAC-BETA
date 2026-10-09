# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ModuleSpec, NavEntry, PermissionSpec, PluginManifest, SettingsNamespace
from apps.core.registry import Registry

manifest = PluginManifest(key="content", name="Screen content", version="0.1.0", kind="module")


def register(r: Registry) -> None:
    from . import api

    r.module(ModuleSpec(key="content", name=str(_("Screen content")), order=31, category="screens",
                        depends_on=("screens",),
                        description=str(_("Themes, fonts and the asset library for screens; layouts, widgets "
                                          "and playlists build on them."))))
    r.permissions_([
        PermissionSpec("content.view", str(_("See themes, fonts and assets"))),
        PermissionSpec("content.edit", str(_("Upload assets and fonts, edit themes"))),
    ])
    r.nav(NavEntry(module="content", label=str(_("Design & assets")), url_name="content:index",
                   permission="content.view", section="content", order=20))
    r.settings_namespace(SettingsNamespace(
        key="content", title=str(_("Screen content")), module="content", levels=("instance", "event"), order=31,
        schema={
            "type": "object",
            "properties": {
                "max_upload_mb": {"type": "integer", "title": "Maximum upload size (MB)", "minimum": 1,
                                  "maximum": 4096, "default": 512},
                "image_max_px": {"type": "integer", "title": "Largest image edge after optimisation (px)",
                                 "minimum": 640, "maximum": 8192, "default": 3840},
                "avif": {"type": "boolean", "title": "Also create AVIF images", "default": True,
                         "description": "Smaller than WebP; players pick what they support."},
                "video_webm": {"type": "boolean", "title": "Also create VP9/WebM videos", "default": True,
                               "description": "H.264/MP4 is always created. VP9 takes longer to encode."},
            },
        },
    ))
    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
