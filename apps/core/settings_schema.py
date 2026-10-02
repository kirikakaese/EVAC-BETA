# SPDX-License-Identifier: AGPL-3.0-or-later
"""Typed settings: JSON-schema validation and inheritance resolution (pure functions).

A settings namespace is a JSON schema of type ``object``. Values are stored per scope level
(``instance -> venue -> event -> screen_group -> screen``); a more specific level overrides a more general
one key by key. :func:`resolve` returns the effective values plus where each value came from, which the UI
uses for its "overridden here" / "inherited from ..." markers.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import jsonschema

DEFAULT = "default"


@dataclass(frozen=True)
class Resolved:
    values: dict[str, Any]
    source: dict[str, str] = field(default_factory=dict)

    def overridden_at(self, level: str) -> list[str]:
        return sorted(k for k, src in self.source.items() if src == level)


def properties(schema: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    props = schema.get("properties", {})
    return dict(props) if isinstance(props, Mapping) else {}


def defaults(schema: Mapping[str, Any]) -> dict[str, Any]:
    return {k: p["default"] for k, p in properties(schema).items() if "default" in p}


def validate(schema: Mapping[str, Any], values: Mapping[str, Any], partial: bool = True) -> list[str]:
    """Return human-readable errors (empty list = valid). ``partial`` ignores ``required``."""
    check = dict(schema)
    if partial:
        check.pop("required", None)
    check.setdefault("additionalProperties", False)
    validator = jsonschema.Draft202012Validator(check, format_checker=jsonschema.FormatChecker())
    errors = []
    for err in sorted(validator.iter_errors(dict(values)), key=lambda e: list(e.absolute_path)):
        where = ".".join(str(p) for p in err.absolute_path)
        errors.append(f"{where}: {err.message}" if where else err.message)
    return errors


def resolve(schema: Mapping[str, Any], layers: Sequence[tuple[str, Mapping[str, Any]]]) -> Resolved:
    """Merge ``[(level, values), ...]`` (most general first) on top of the schema defaults.

    Unknown keys (e.g. left over from an older schema version) are ignored.
    """
    known = properties(schema)
    values = defaults(schema)
    source = dict.fromkeys(values, DEFAULT)
    for level, layer in layers:
        for key, value in layer.items():
            if key in known:
                values[key] = value
                source[key] = level
    return Resolved(values, source)


def coerce(prop: Mapping[str, Any], raw: Any) -> Any:
    """Convert a submitted form value to the property's JSON type (best effort, validation follows)."""
    typ = prop.get("type")
    if raw is None:
        return None
    if typ == "boolean":
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in ("1", "true", "on", "yes")
    if typ == "integer":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return raw
    if typ == "number":
        try:
            return float(raw)
        except (TypeError, ValueError):
            return raw
    if typ == "array":
        if isinstance(raw, list):
            return raw
        return [s.strip() for s in str(raw).replace("\n", ",").split(",") if s.strip()]
    return raw
