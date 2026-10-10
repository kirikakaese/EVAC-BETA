# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event snapshots for venue nodes (ADR-0002, ADR-0036): build on central, apply on the node.

A snapshot holds, per synced model (``r.sync``), the event's rows in Django's serialisation format, plus the media
files the node must have. Its ``version`` is a hash of everything except sealed secrets, so it changes exactly
when the configuration changes (the ETag). Secrets travel sealed for the receiving node.
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
from collections.abc import Iterator
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.db import models, transaction

from apps.core import crypto
from apps.core.plugins import SyncModel, SyncSpec
from apps.core.registry import registry

from . import keys

FORMAT = 1
_applying: contextvars.ContextVar[bool] = contextvars.ContextVar("evac_node_applying", default=False)


def applying() -> bool:
    """True while a snapshot or op-log is being applied (changes then are not recorded again)."""
    return _applying.get()


@contextlib.contextmanager
def applying_changes() -> Iterator[None]:
    token = _applying.set(True)
    try:
        yield
    finally:
        _applying.reset(token)


def specs() -> list[SyncSpec]:
    return sorted(registry.ensure_loaded().sync_specs.values(), key=lambda s: (s.order, s.module))


def sync_models(*, live: bool | None = None) -> list[SyncModel]:
    return [m for s in specs() for m in s.models if live is None or m.live == live]


def live_labels() -> set[str]:
    return {m.label.lower() for m in sync_models(live=True)}


def model_of(label: str) -> type[models.Model]:
    return apps.get_model(label)


def serialize(objs: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(serializers.serialize("json", objs))
    return rows


def canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _media_rel(path: Any) -> str:
    import os

    return os.path.relpath(str(path), str(settings.MEDIA_ROOT)).replace("\\", "/")


def files_of(event: Any, *, live: bool = False) -> list[list[str]]:
    out: dict[str, str] = {}
    for m in sync_models():
        if m.files is None or (m.live and not live):
            continue
        for obj in m.queryset(event):
            for path, sha in m.files(obj):
                rel = _media_rel(path) if str(path).startswith(str(settings.MEDIA_ROOT)) else str(path)
                if rel and not rel.startswith(".."):
                    out[rel] = sha or ""
    return [[p, s] for p, s in sorted(out.items())]


def build(event: Any, *, seed: bool = False, box_public: str = "") -> dict[str, Any]:
    """The event's snapshot. ``seed`` adds the live models (first sync of a checkout). Secrets are sealed for
    ``box_public``; without it they are left out."""
    data: dict[str, list[dict[str, Any]]] = {}
    for m in sync_models():
        if m.live and not seed:
            continue
        rows = serialize(m.queryset(event).order_by("pk"))
        for row in rows:
            for f in m.secret_fields:
                value = row["fields"].get(f) or ""
                # stable for the version hash; replaced by the sealed value below
                row["fields"][f] = "hash:" + hashlib.sha256(str(value).encode()).hexdigest() if value else ""
        data[m.label.lower()] = rows
    body: dict[str, Any] = {"format": FORMAT, "event": event.slug, "event_id": str(event.pk), "seed": seed,
                            "models": data, "files": files_of(event, live=seed)}
    body["version"] = _version(body)
    for m in sync_models():
        if not m.secret_fields or m.label.lower() not in data:
            continue
        objs = {str(o.pk): o for o in m.queryset(event)}
        for row in data[m.label.lower()]:
            obj = objs.get(str(row["pk"]))
            for f in m.secret_fields:
                raw = getattr(obj, f, "") if obj is not None else ""
                row["fields"][f] = _seal(raw, box_public) if raw and box_public else ""
    return body


def _version(body: dict[str, Any]) -> str:
    """Hash of the configuration, without the node's own fields (central's copies of them change all the time)."""
    local = {m.label.lower(): m.local_fields for m in sync_models() if m.local_fields}
    stripped = {**body, "models": {label: [{**r, "fields": {k: v for k, v in r["fields"].items()
                                                              if k not in local.get(label, ())}} for r in rows]
                                   for label, rows in body["models"].items()}}
    return hashlib.sha256(canonical(stripped).encode()).hexdigest()[:32]


def _seal(ciphertext: str, box_public: str) -> str:
    try:
        plain = crypto.decrypt(ciphertext)
    except Exception:  # noqa: BLE001 - an unreadable secret is left out, never sent in the clear
        return ""
    return keys.seal(box_public, plain)


def _unseal(value: str, box_private: str) -> str:
    if not value or not value.startswith(keys.SEALED):
        return ""
    return crypto.encrypt(keys.open_sealed(box_private, value))


def _user_fks(model: type[models.Model]) -> list[models.ForeignKey]:
    user_model = apps.get_model(settings.AUTH_USER_MODEL)
    return [f for f in model._meta.fields
            if isinstance(f, models.ForeignKey) and f.related_model is user_model and f.null]


def apply(data: dict[str, Any], *, box_private: str = "") -> Any:
    """Make the local database match ``data`` (on a node). Returns the event. Runs in one transaction; changes
    are not recorded in the op-log."""
    if data.get("format") != FORMAT:
        raise ValueError(f"unsupported snapshot format {data.get('format')!r}")
    event_model = apps.get_model("events", "Event")
    seed = bool(data.get("seed"))
    user_model = apps.get_model(settings.AUTH_USER_MODEL)
    with transaction.atomic(), applying_changes():
        kept: dict[str, set[Any]] = {}
        order = [m for m in sync_models() if m.label.lower() in data["models"] and (seed or not m.live)]
        users = set(user_model.objects.values_list("pk", flat=True))
        for m in order:
            model = model_of(m.label)
            user_fields = _user_fks(model)
            keep: set[Any] = set()
            for row in data["models"][m.label.lower()]:
                row = {"model": row["model"], "pk": row.get("pk"), "fields": dict(row["fields"])}
                for f in m.secret_fields:
                    row["fields"][f] = _unseal(row["fields"].get(f) or "", box_private) if box_private else ""
                for f in user_fields:  # people who are not on this node (e.g. a former editor) become "unknown"
                    ref = row["fields"].get(f.name)
                    if ref is not None and _pk(user_model, ref) not in users:
                        row["fields"][f.name] = None
                if m.natural_key:
                    lookup = {k: row["fields"].get(k) for k in m.natural_key}
                    existing = model.objects.filter(**{(f"{k}_id" if isinstance(model._meta.get_field(k),
                                                                                 models.ForeignKey) else k): v
                                                       for k, v in lookup.items()}).first()
                    row["pk"] = existing.pk if existing is not None else None
                else:
                    existing = model.objects.filter(pk=row["pk"]).first()
                for obj in serializers.deserialize("python", [row]):
                    if existing is not None:
                        for f in m.local_fields:
                            setattr(obj.object, f, getattr(existing, f))
                    obj.save()
                    keep.add(obj.object.pk)
                if model is user_model:
                    users.add(_pk(user_model, row["pk"]))
            kept[m.label.lower()] = keep
        event = event_model.objects.get(pk=data["event_id"])
        for m in reversed(order):
            if m.delete_missing:
                for obj in m.queryset(event).exclude(pk__in=kept[m.label.lower()]):
                    obj.delete()
    return event


def _pk(model: type[models.Model], value: Any) -> Any:
    try:
        return model._meta.pk.to_python(value)
    except Exception:  # noqa: BLE001
        return value


def missing_files(data: dict[str, Any]) -> list[list[str]]:
    from pathlib import Path

    root = Path(settings.MEDIA_ROOT)
    return [[p, s] for p, s in data.get("files", []) if not (root / p).exists()]
