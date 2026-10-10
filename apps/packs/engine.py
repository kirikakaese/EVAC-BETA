# SPDX-License-Identifier: AGPL-3.0-or-later
"""Export and import across sections (ADR-0024). Sections are registered by modules
(``r.pack_section(PackSectionSpec(...))``); this module only resolves dependencies, remaps ids and calls them."""
from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps.core import modules
from apps.core.plugins import PackSectionSpec
from apps.core.registry import registry

from . import packfile


def sections(event=None) -> list[PackSectionSpec]:
    """Registered sections in load order (only those whose module is on, when ``event`` is given)."""
    out = sorted(registry.ensure_loaded().pack_sections.values(), key=lambda s: (s.order, s.key))
    if event is not None:
        out = [s for s in out if modules.is_enabled(s.module, event)]
    return out


def closure(event, selection: Mapping[str, set[str]]) -> dict[str, set[str]]:
    """The selection plus everything it needs (fixpoint over ``requires``)."""
    specs = {s.key: s for s in sections(event)}
    owned: dict[str, set[str]] | None = None
    chosen: dict[str, set[str]] = {k: set(v) for k, v in selection.items() if k in specs and v}
    todo = dict(chosen)
    while todo:
        nxt: dict[str, set[str]] = {}
        for key, ids in todo.items():
            spec = specs[key]
            if not spec.requires:
                continue
            for dep_key, dep_ids in spec.requires(event, ids).items():
                if dep_key == "*":
                    if owned is None:
                        owned = {k: {i for i, _label in s.choices(event)} for k, s in specs.items()}
                    targets = [(k, set(dep_ids) & ids_of) for k, ids_of in owned.items()]
                else:
                    targets = [(dep_key, set(dep_ids))] if dep_key in specs else []
                for k, wanted in targets:
                    new = wanted - chosen.get(k, set())
                    if new:
                        chosen.setdefault(k, set()).update(new)
                        nxt.setdefault(k, set()).update(new)
        todo = nxt
    return chosen


def dump(event, selection: Mapping[str, set[str]]) -> tuple[dict[str, list[dict[str, Any]]], packfile.FileSet,
                                                           list[str]]:
    """Sections, files and needed modules for a selection (dependencies included)."""
    files = packfile.FileSet()
    out: dict[str, list[dict[str, Any]]] = {}
    mods: list[str] = []
    chosen = closure(event, selection)
    for spec in sections(event):
        ids = chosen.get(spec.key)
        if not ids:
            continue
        items = spec.dump(event, ids, files)
        if items:
            out[spec.key] = items
            mods.append(spec.module)
    return out, files, mods


class ImportContext:
    """Handed to ``PackSectionSpec.load``: id mapping, packed files, the acting user and warnings."""

    def __init__(self, *, event, actor, request, path: Path | None, max_bytes: int):
        self.event, self.actor, self.request = event, actor, request
        self.path, self.max_bytes = path, max_bytes
        self.ids: dict[str, str] = {}
        self.warnings: list[str] = []
        self._tmp = tempfile.TemporaryDirectory(prefix="evac-pack-")

    def remap(self, value: Any) -> Any:
        """Replace every string that is a known pack id by the new id (deeply, in JSON values)."""
        if isinstance(value, str):
            return self.ids.get(value, value)
        if isinstance(value, list):
            return [self.remap(v) for v in value]
        if isinstance(value, dict):
            return {k: self.remap(v) for k, v in value.items()}
        return value

    def file(self, ref: str) -> Path:
        if self.path is None or not isinstance(ref, str) or not packfile.FILE_RE.match(f"files/{ref}"):
            raise packfile.PackError("A file is missing from the pack.")
        return packfile.extract(self.path, ref, Path(self._tmp.name) / ref, max_bytes=self.max_bytes)

    def warn(self, text: str) -> None:
        self.warnings.append(str(text))

    def close(self) -> None:
        self._tmp.cleanup()


def missing_modules(event, pack: packfile.Pack) -> list[str]:
    """Sections in the pack this event cannot import (unknown section or module off)."""
    known = {s.key: s for s in sections()}
    out = []
    for key in pack.sections:
        spec = known.get(key)
        if spec is None:
            out.append(key)
        elif not modules.is_enabled(spec.module, event):
            out.append(spec.module)
    return sorted(set(out))


def load(event, pack: packfile.Pack, *, actor, request=None, path: Path | None, max_bytes: int) -> dict[str, Any]:
    """Create the pack's objects in ``event`` (the caller wraps this in a transaction)."""
    ctx = ImportContext(event=event, actor=actor, request=request, path=path, max_bytes=max_bytes)
    created: dict[str, list[str]] = {}
    try:
        for spec in sections(event):
            items = pack.sections.get(spec.key)
            if items:
                labels = spec.load(event, items, ctx)
                if labels:
                    created[spec.key] = labels
    finally:
        ctx.close()
    return {"created": created, "warnings": ctx.warnings}
