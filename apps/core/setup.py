# SPDX-License-Identifier: AGPL-3.0-or-later
"""The setup checklist on the event overview (ADR-0050): what is still missing for an event.

Items come from plugins (``r.setup_check(SetupCheckSpec(...))``); checks of modules that are off are not called.
Organisers (``events.manage``) see the card until every required item is done, or until they hide it for the event
(setting ``setup.checklist_hidden``).
"""
from __future__ import annotations

import logging
from typing import Any

from django.urls import NoReverseMatch, reverse

from . import modules, settings_store
from .plugins import SetupResult
from .registry import registry

log = logging.getLogger("evac.setup")

NAMESPACE = "setup"


def items(event, request=None) -> list[dict[str, Any]]:
    """``[{"key", "label", "help", "done", "optional", "detail", "url", "module"}]`` in checklist order."""
    out: list[dict[str, Any]] = []
    for spec in sorted(registry.ensure_loaded().setup_checks.values(), key=lambda s: (s.order, s.key)):
        if not modules.is_enabled(spec.module, event):
            continue
        try:
            result = spec.check(event, request)
        except Exception:  # a broken check must not break the overview page
            log.exception("setup check %s failed", spec.key)
            continue
        if result is None:
            continue
        if not isinstance(result, SetupResult):
            result = SetupResult(status=result)
        url = result.url
        if not url:
            try:
                url = spec.url(event) if spec.url is not None else (
                    reverse(spec.url_name, args=[event.slug]) if spec.url_name else "")
            except NoReverseMatch:
                url = ""
        out.append({"key": spec.key, "label": spec.label, "help": spec.help, "done": result.status == "done",
                    "optional": spec.optional, "detail": result.detail, "url": url, "module": spec.module})
    return out


def is_hidden(event) -> bool:
    return bool(settings_store.get(NAMESPACE, event=event).get("checklist_hidden"))


def set_hidden(event, hidden: bool, *, user=None, request=None) -> None:
    """Hide or show the checklist for ``event`` (audit-logged through the settings store)."""
    values = dict(settings_store.raw(NAMESPACE, "event", str(event.pk)))
    if hidden:
        values["checklist_hidden"] = True
    else:
        values.pop("checklist_hidden", None)
    settings_store.save(NAMESPACE, "event", str(event.pk), values, user=user, event=event, request=request)


def card(event, request) -> dict[str, Any] | None:
    """Context of the overview card, or None when it is hidden or nothing required is left to do."""
    if is_hidden(event):
        return None
    rows = items(event, request)
    open_required = [r for r in rows if not r["done"] and not r["optional"]]
    if not open_required:
        return None
    return {"items": rows, "open": len(open_required), "total": len([r for r in rows if not r["optional"]])}
