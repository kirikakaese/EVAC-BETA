# SPDX-License-Identifier: AGPL-3.0-or-later
"""Themes, fonts, assets and layouts for venue nodes (ADR-0036): the event's own and the shared ones."""
from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.core.plugins import SyncModel, SyncSpec


def _mine(e: Any) -> Q:
    return Q(event=e) | Q(event__isnull=True)


def _asset_files(asset: Any) -> list[tuple[str, str]]:
    from . import storage

    out = []
    for name, variant in (asset.variants or {}).items():
        file_name = (variant or {}).get("file")
        if file_name:
            try:
                out.append((str(storage.path(asset.sha256, file_name)), asset.sha256 if name == "original" else ""))
            except ValueError:
                continue
    return out


def _font_files(font: Any) -> list[tuple[str, str]]:
    from . import storage

    if not font.sha256:
        return []
    return [(str(storage.path(font.sha256, "font.woff2")), "")]


def spec() -> SyncSpec:
    from .models import Asset, AssetFolder, FontFamily, FontFile, Layout, LayoutVersion, Theme

    return SyncSpec(module="content", order=100, models=(
        SyncModel("content.FontFamily", lambda e: FontFamily.objects.filter(_mine(e))),
        SyncModel("content.FontFile", lambda e: FontFile.objects.filter(Q(family__event=e)
                                                                        | Q(family__event__isnull=True)),
                  files=_font_files),
        SyncModel("content.Theme", lambda e: Theme.objects.filter(_mine(e))),
        SyncModel("content.AssetFolder", lambda e: AssetFolder.objects.filter(_mine(e))),
        SyncModel("content.Asset", lambda e: Asset.objects.filter(_mine(e)), files=_asset_files),
        SyncModel("content.Layout", lambda e: Layout.objects.filter(_mine(e))),
        SyncModel("content.LayoutVersion", lambda e: LayoutVersion.objects.filter(Q(layout__event=e)
                                                                                  | Q(layout__event__isnull=True))),
    ))
