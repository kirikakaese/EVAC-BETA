# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in packs (ADR-0024): ``gallery/<key>.json`` files with ``name``, ``description`` and ``sections`` in
the pack format. They ship with EVAC (no signature needed) and are turned into a pack when chosen."""
from __future__ import annotations

import datetime as dt
import functools
import io
import json
from pathlib import Path
from typing import Any

import evac

from . import packfile

DIR = Path(__file__).resolve().parent / "gallery"


@functools.cache
def entries() -> dict[str, dict[str, Any]]:
    out = {}
    for path in sorted(DIR.glob("*.json")):
        data = json.loads(path.read_text())
        out[path.stem] = {"key": path.stem, **data}
    return out


def get(key: str) -> dict[str, Any] | None:
    return entries().get(key)


def build(entry: dict[str, Any]) -> bytes:
    out = io.BytesIO()
    packfile.write(out, name=entry["name"], description=entry.get("description", ""), sections=entry["sections"],
                   files=packfile.FileSet(), modules=entry.get("modules", []), generator=f"EVAC {evac.__version__}",
                   signer=None, created=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    return out.getvalue()
