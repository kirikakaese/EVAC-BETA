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


def chain(*, venue=None, event=None, screen_group=None, screen_groups=(), screen=None) -> list[tuple[str, str]]:
    """Scope levels from the most general to the most specific. ``screen_groups`` (a screen's groups, in
    order) are applied one after the other, so a later group wins over an earlier one."""
    out = [("instance", "")]
    if venue is not None:
        out.append(("venue", str(venue.pk)))
    if event is not None:
        out.append(("event", str(event.pk)))
    if screen_group is not None:
        out.append(("screen_group", str(screen_group.pk)))
    out.extend(("screen_group", str(g.pk)) for g in screen_groups)
    if screen is not None:
        out.append(("screen", str(screen.pk)))
    return out


def _layers(ns_key: str, scopes: list[tuple[str, str]]) -> list[tuple[str, dict[str, Any]]]:
    from django.db.models import Q

    from .models import SettingValue

    if not scopes:
        return []
    # exactly the rows of these scopes (not every screen's row of the namespace)
    match = Q()
    for lvl, sid in scopes:
        match |= Q(level=lvl, scope_id=sid)
    rows = {(r.level, r.scope_id): r.values for r in SettingValue.objects.filter(namespace=ns_key).filter(match)}
    return [(lvl, rows.get((lvl, sid), {})) for lvl, sid in scopes]


def resolve(ns_key: str, **objs) -> settings_schema.Resolved:
    ns = namespace(ns_key)
    scopes = [s for s in chain(**objs) if s[0] in ns.levels]
    return settings_schema.resolve(ns.schema, _layers(ns_key, scopes))


def get(ns_key: str, **objs) -> dict[str, Any]:
    return resolve(ns_key, **objs).values


def get_many(ns_key: str, screens: list[Any], *, event: Any = None, venue: Any = None) -> dict[str, dict[str, Any]]:
    """``get(ns_key, event=…, screen=s)`` for many screens with one query (an alarm reaches every screen):
    ``{screen id: values}``. Screen groups are not part of the chain, as in ``get(…, screen=s)``."""
    from .models import SettingValue

    ns = namespace(ns_key)
    base = [s for s in chain(venue=venue, event=event) if s[0] in ns.levels]
    with_screen = "screen" in ns.levels
    wanted = {(lvl, sid) for lvl, sid in base} | ({("screen", str(s.pk)) for s in screens} if with_screen else set())
    rows = {(r.level, r.scope_id): r.values for r in SettingValue.objects.filter(
        namespace=ns_key, level__in={lvl for lvl, _ in wanted}) if (r.level, r.scope_id) in wanted}
    layers = [(lvl, rows.get((lvl, sid), {})) for lvl, sid in base]
    out = {}
    for s in screens:
        mine = layers + ([("screen", rows.get(("screen", str(s.pk)), {}))] if with_screen else [])
        out[str(s.pk)] = settings_schema.resolve(ns.schema, mine).values
    return out


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
