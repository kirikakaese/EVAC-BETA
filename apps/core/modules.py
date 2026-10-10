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
