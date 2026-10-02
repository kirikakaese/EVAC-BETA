# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings framework: read/write values of a :class:`~apps.core.plugins.SettingsNamespace` per scope.

    from apps.core import settings_store
    values = settings_store.get("branding", event=event)          # effective dict
    resolved = settings_store.resolve("branding", event=event)    # values + provenance per key
    settings_store.save("branding", "event", str(event.pk), {"primary_color": "#ff0000"}, user=u)

The chain is built from the most specific object given: a screen implies its group and event, an event
implies the instance (and, when exactly one venue is passed, that venue).
"""
from __future__ import annotations

from typing import Any

from . import settings_schema
from .plugins import SETTINGS_LEVELS
from .registry import registry


class SettingsError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def namespace(key: str):
    ns = registry.ensure_loaded().settings_namespaces.get(key)
    if ns is None:
        raise KeyError(f"unknown settings namespace {key!r}")
    return ns


def chain(*, venue=None, event=None, screen_group=None, screen=None) -> list[tuple[str, str]]:
    out = [("instance", "")]
    if venue is not None:
        out.append(("venue", str(venue.pk)))
    if event is not None:
        out.append(("event", str(event.pk)))
    if screen_group is not None:
        out.append(("screen_group", str(screen_group.pk)))
    if screen is not None:
        out.append(("screen", str(screen.pk)))
    return out


def _layers(ns_key: str, scopes: list[tuple[str, str]]) -> list[tuple[str, dict[str, Any]]]:
    from .models import SettingValue

    rows = {(r.level, r.scope_id): r.values for r in SettingValue.objects.filter(namespace=ns_key)
            .filter(level__in=[lvl for lvl, _ in scopes])}
    return [(lvl, rows.get((lvl, sid), {})) for lvl, sid in scopes]


def resolve(ns_key: str, **objs) -> settings_schema.Resolved:
    ns = namespace(ns_key)
    scopes = [s for s in chain(**objs) if s[0] in ns.levels]
    return settings_schema.resolve(ns.schema, _layers(ns_key, scopes))


def get(ns_key: str, **objs) -> dict[str, Any]:
    return resolve(ns_key, **objs).values


def raw(ns_key: str, level: str, scope_id: str = "") -> dict[str, Any]:
    from .models import SettingValue

    row = SettingValue.objects.filter(namespace=ns_key, level=level, scope_id=scope_id).first()
    return dict(row.values) if row else {}


def save(ns_key: str, level: str, scope_id: str, values: dict[str, Any], *, user=None, event=None,
         request=None) -> dict[str, Any]:
    """Replace the values stored at one level (keys absent from ``values`` inherit again)."""
    from .audit import log
    from .models import SettingValue

    ns = namespace(ns_key)
    if level not in SETTINGS_LEVELS or level not in ns.levels:
        raise SettingsError([f"namespace {ns_key} cannot be set at level {level}"])
    errors = settings_schema.validate(ns.schema, values)
    if errors:
        raise SettingsError(errors)
    before = raw(ns_key, level, scope_id)
    if values:
        SettingValue.objects.update_or_create(namespace=ns_key, level=level, scope_id=scope_id,
                                              defaults={"values": values, "updated_by": user})
    else:
        SettingValue.objects.filter(namespace=ns_key, level=level, scope_id=scope_id).delete()
    changed = {k: [before.get(k), values.get(k)] for k in set(before) | set(values) if before.get(k) != values.get(k)}
    if changed:
        log(action="settings.changed", actor=user, event=event, request=request,
            message=f"Settings {ns.title} changed at {level} level", changes=changed,
            scope={"namespace": ns_key, "level": level, "scope_id": scope_id})
    return values
