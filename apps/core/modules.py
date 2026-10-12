# SPDX-License-Identifier: AGPL-3.0-or-later
"""Module on/off state: instance-wide (admins) and per event (orga), with dependencies.

A module is *active* for an event when it is installed (registered), switched on at instance level,
not switched off for the event, and every module it depends on is active as well. Required modules are
always active.
"""
from __future__ import annotations

from functools import wraps

from django.core.cache import cache
from django.http import Http404

from .registry import registry

CACHE_KEY = "evac:modules:v1"


def _instance_states() -> dict[str, bool]:
    states = cache.get(CACHE_KEY)
    if states is None:
        from .models import ModuleState

        states = dict(ModuleState.objects.values_list("key", "enabled"))
        cache.set(CACHE_KEY, states, 30)
    return states


def invalidate() -> None:
    cache.delete(CACHE_KEY)


def instance_enabled(key: str) -> bool:
    spec = registry.ensure_loaded().modules.get(key)
    if spec is None:
        return False
    if spec.required:
        return True
    return _instance_states().get(key, spec.default_enabled)


def _event_states(event) -> dict[str, bool]:
    cached = getattr(event, "_module_states", None)
    if cached is None:
        cached = dict(event.module_states.values_list("key", "enabled"))
        event._module_states = cached
    return cached


def is_enabled(key: str, event=None, _seen: frozenset[str] = frozenset()) -> bool:
    spec = registry.ensure_loaded().modules.get(key)
    if spec is None or key in _seen:
        return False
    if spec.required:
        return True
    if not instance_enabled(key):
        return False
    if event is not None and spec.event_toggle and _event_states(event).get(key) is False:
        return False
    return all(is_enabled(dep, event, _seen | {key}) for dep in spec.depends_on)


def status(event=None) -> list[dict]:
    """Rows for the Settings -> Modules page."""
    reg = registry.ensure_loaded()
    inst = _instance_states()
    ev = _event_states(event) if event is not None else {}
    rows = []
    for spec in sorted(reg.modules.values(), key=lambda s: (s.order, s.name)):
        rows.append({
            "spec": spec,
            "instance": True if spec.required else inst.get(spec.key, spec.default_enabled),
            "instance_overridden": spec.key in inst,
            "event": ev.get(spec.key),
            "active": is_enabled(spec.key, event),
            "dependants": sorted(s.key for s in reg.modules.values() if spec.key in s.depends_on),
            "missing_deps": [d for d in spec.depends_on if not is_enabled(d, event)],
            "needs_ack": acknowledgement_needed(spec.key, event) if event is not None else False,
        })
    return rows


def set_instance(key: str, enabled: bool, user=None, request=None) -> None:
    from .audit import log
    from .models import ModuleState

    spec = registry.ensure_loaded().modules[key]
    if spec.required:
        raise ValueError(f"module {key} is required")
    before = instance_enabled(key)
    ModuleState.objects.update_or_create(key=key, defaults={"enabled": enabled, "updated_by": user})
    invalidate()
    log(action="module.toggled", actor=user, request=request,
        message=f"Module {spec.name} {'on' if enabled else 'off'}",
        changes={"enabled": [before, enabled]}, scope={"module": key, "level": "instance"})


def set_event(event, key: str, enabled: bool | None, user=None, request=None) -> None:
    """``enabled=None`` removes the override (follow the instance state)."""
    from .audit import log
    from .models import EventModuleState

    spec = registry.ensure_loaded().modules[key]
    if spec.required or not spec.event_toggle:
        raise ValueError(f"module {key} cannot be toggled per event")
    before = _event_states(event).get(key)
    if enabled is None:
        EventModuleState.objects.filter(event=event, key=key).delete()
    else:
        EventModuleState.objects.update_or_create(event=event, key=key,
                                                  defaults={"enabled": enabled, "updated_by": user})
    if hasattr(event, "_module_states"):
        del event._module_states
    log(action="module.toggled", actor=user, event=event, target=event, request=request,
        message=f"Module {spec.name}: {'inherit' if enabled is None else ('on' if enabled else 'off')}",
        changes={"enabled": [before, enabled]}, scope={"module": key, "level": "event"})


def blocked_reason(key: str, user) -> str:
    """Why ``user`` cannot switch the module on for an event ("" = they can, given the event permission).

    A module that is off for the whole instance has to be switched on there first, and only instance admins may do
    that."""
    from django.utils.translation import gettext as _

    spec = registry.ensure_loaded().modules.get(key)
    if spec is None:
        return _("This module is not installed.")
    if instance_enabled(key) or getattr(user, "is_superuser", False):
        return ""
    return _("Switched off for this server. Only an instance admin can switch it on.")


def with_dependencies(keys) -> set[str]:
    """``keys`` plus every installed module they depend on (transitively)."""
    reg = registry.ensure_loaded().modules
    out: set[str] = set()
    todo = [k for k in keys if k in reg]
    while todo:
        key = todo.pop()
        if key not in out:
            out.add(key)
            todo.extend(d for d in reg[key].depends_on if d in reg)
    return out


def _own_on(key: str, event) -> bool:
    """On at instance level and not switched off for the event (dependencies aside)."""
    spec = registry.ensure_loaded().modules[key]
    return spec.required or (instance_enabled(key) and (not spec.event_toggle or _event_states(event).get(key)
                                                        is not False))


def switch_on(event, key: str, *, user=None, request=None) -> None:
    """Switch a module (and the modules it depends on) on for ``event``, at instance level too where it is off
    there (instance admins only: ``PermissionError`` otherwise). Accepting its statement is a separate step
    (:func:`acknowledge`)."""
    reg = registry.ensure_loaded().modules
    for dep in reg[key].depends_on:
        if dep in reg and not reg[dep].required:
            switch_on(event, dep, user=user, request=request)
    spec = reg[key]
    if _own_on(key, event):
        return
    if not instance_enabled(key):
        if blocked_reason(key, user):
            raise PermissionError(f"module {key} is off for the instance")
        set_instance(key, True, user=user, request=request)
    if spec.event_toggle and not _own_on(key, event):
        set_event(event, key, True, user=user, request=request)


def apply_selection(event, wanted, *, user=None, request=None) -> dict[str, list[str]]:
    """Make exactly ``wanted`` (plus dependencies) the modules of ``event`` (event setup wizard, ADR-0050).

    Returns ``{"on", "off", "unavailable", "pending"}`` (module keys): modules the user may not switch on stay off
    (``unavailable``); modules with a statement nobody accepted for the event yet stay off until it is accepted
    (``pending``, see :func:`acknowledge` and :func:`switch_on`). Required modules and modules without a per-event
    switch are left alone."""
    reg = registry.ensure_loaded().modules
    wanted = with_dependencies(wanted)
    result: dict[str, list[str]] = {"on": [], "off": [], "unavailable": [], "pending": []}
    blocked: set[str] = set()
    for spec in sorted(reg.values(), key=lambda s: (s.order, s.key)):
        if spec.required or not spec.event_toggle:
            continue
        key = spec.key
        if key in wanted and any(d in blocked for d in spec.depends_on):
            blocked.add(key)
            result["unavailable"].append(key)
            continue
        if key in wanted and blocked_reason(key, user):
            blocked.add(key)
            result["unavailable"].append(key)
            continue
        if key in wanted and acknowledgement_needed(key, event):
            result["pending"].append(key)
            key_wanted = False
        else:
            key_wanted = key in wanted
        if key_wanted and not _own_on(key, event):
            switch_on(event, key, user=user, request=request)
            result["on"].append(key)
        elif not key_wanted and _own_on(key, event):
            set_event(event, key, False, user=user, request=request)
            result["off"].append(key)
    return result


def acknowledgement_needed(key: str, event) -> bool:
    """The module has a statement (``ModuleSpec.acknowledgement``) nobody accepted for ``event`` yet."""
    from .models import ModuleAcknowledgement

    spec = registry.ensure_loaded().modules.get(key)
    if spec is None or not spec.acknowledgement or event is None:
        return False
    return not ModuleAcknowledgement.objects.filter(event=event, key=key).exists()


def acknowledgement(key: str, event):
    from .models import ModuleAcknowledgement

    return ModuleAcknowledgement.objects.filter(event=event, key=key).select_related("accepted_by").first()


def acknowledge(event, key: str, user=None, request=None):
    """Record that ``user`` accepted the module's statement for ``event`` (audit-logged; once per event)."""
    from .audit import log
    from .models import ModuleAcknowledgement

    spec = registry.ensure_loaded().modules[key]
    if not spec.acknowledgement:
        raise ValueError(f"module {key} has no statement to accept")
    row, created = ModuleAcknowledgement.objects.get_or_create(event=event, key=key, defaults={
        "statement": str(spec.acknowledgement), "accepted_by": user if getattr(user, "pk", None) else None,
        "accepted_by_repr": str(user or "system")[:200]})
    if created:
        log(action="module.acknowledged", actor=user, event=event, target=event, request=request,
            message=f"{spec.name}: statement accepted", scope={"module": key},
            changes={"statement": [None, str(spec.acknowledgement)]})
    return row


def require_module(key: str):
    """View decorator: 404 when the module is not active for ``request.event`` (or instance-wide)."""

    def deco(fn):
        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            event = kwargs.get("event") or getattr(request, "event", None)
            if not is_enabled(key, event):
                raise Http404("Module disabled")
            return fn(request, *args, **kwargs)

        wrapper.evac_module = key
        return wrapper

    return deco
