# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inventory on venue nodes (ADR-0036): items and loans are live on the node during a checkout, so lending at the
counter works without central."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def _files(*names: str):  # type: ignore[no-untyped-def]
    def files(obj):  # type: ignore[no-untyped-def]
        return [(getattr(obj, n).name, "") for n in names if getattr(obj, n)]
    return files


def spec() -> SyncSpec:
    from .models import Category, Item, Loan, Note

    return SyncSpec(module="inventory", order=180, models=(
        SyncModel("inventory.Category", lambda e: Category.objects.filter(event=e)),
        SyncModel("inventory.Item", lambda e: Item.objects.filter(event=e), live=True, files=_files("photo")),
        SyncModel("inventory.Loan", lambda e: Loan.objects.filter(item__event=e), live=True,
                  files=_files("signature", "photo_out", "photo_back")),
        SyncModel("inventory.Note", lambda e: Note.objects.filter(item__event=e), live=True),
    ))
