# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extension configuration services: effective config, save, test, webhook secret, purge, signatures."""
from __future__ import annotations

import hashlib
import hmac
import secrets as pysecrets
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core import crypto, settings_schema
from apps.core.audit import log
from apps.core.plugins import ConnectionResult, ExtensionSpec
from apps.core.registry import registry

from .models import ExtensionConfig, ExtensionLog


class ExtensionError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def specs_for(level: str) -> list[ExtensionSpec]:
    allowed = {"instance": ("instance", "both"), "event": ("event", "both", "instance")}[level]
    return sorted((s for s in registry.ensure_loaded().extensions.values() if s.scope in allowed),
                  key=lambda s: s.name.lower())


def get_config(key: str, event=None) -> ExtensionConfig | None:
    return ExtensionConfig.objects.filter(extension=key, event=event).first()


def instance_config(key: str) -> ExtensionConfig | None:
    return get_config(key, None)


def effective(key: str, event=None) -> ExtensionConfig | None:
    """The configuration that applies for ``event`` (None when the extension is off there)."""
    spec = registry.get_extension(key)
    if spec is None:
        return None
    if event is None:
        cfg = instance_config(key)
        return cfg if cfg is not None and cfg.enabled else None
    row = get_config(key, event)
    if row is not None and not row.use_instance:
        return row if row.enabled and spec.scope != "instance" else None
    if row is not None and not row.enabled:
        return None
    if spec.scope in ("instance", "both"):
        inst = instance_config(key)
        if inst is not None and inst.enabled and (row is not None or spec.scope == "instance"):
            return inst
    return None


def enabled_configs(key: str):
    """Every enabled config row of an extension (instance and events)."""
    return ExtensionConfig.objects.filter(extension=key, enabled=True)


def card_status(spec: ExtensionSpec, event=None) -> str:
    row = get_config(spec.key, event)
    if row is None:
        if event is not None and spec.scope in ("instance",):
            inst = instance_config(spec.key)
            return "instance" if inst is not None and inst.enabled else "not_configured"
        return "not_configured"
    if row.use_instance:
        inst = instance_config(spec.key)
        return "instance" if row.enabled and inst is not None and inst.enabled else "disabled"
    return row.status


def get_or_new(spec: ExtensionSpec, event=None) -> ExtensionConfig:
    row = get_config(spec.key, event)
    if row is None:
        row = ExtensionConfig(extension=spec.key, event=event,
                              features={f.key: f.default_enabled for f in spec.features})
    return row


def write_log(config: ExtensionConfig, level: str, message: str, **details: Any) -> None:
    ExtensionLog.objects.create(config=config, level=level, message=message[:500], details=details)


@transaction.atomic
def save_config(config: ExtensionConfig, *, settings_values: dict[str, Any], secret_values: dict[str, str],
                features: dict[str, bool], enabled: bool, use_instance: bool = False, user=None,
                request=None) -> ExtensionConfig:
    """Validate and store. Blank secret values keep the stored secret; ``"__clear__"`` removes one."""
    spec = config.spec
    if spec is None:
        raise ExtensionError(["extension is not installed"])
    errors = [] if use_instance else settings_schema.validate(spec.settings_schema, settings_values)
    if errors:
        raise ExtensionError(errors)
    before = {"enabled": config.enabled, "settings": dict(config.settings), "features": dict(config.features),
              "use_instance": config.use_instance}
    current = config.secrets if config.is_saved else {}
    changed_secrets = []
    for name, _label in spec.secret_fields:
        new = secret_values.get(name, "")
        if new == "__clear__":
            if name in current:
                current.pop(name)
                changed_secrets.append(name)
        elif new:
            current[name] = new
            changed_secrets.append(name)
    config.settings = settings_values if not use_instance else {}
    config.set_secrets(current)
    config.features = {f.key: bool(features.get(f.key, False)) for f in spec.features}
    config.enabled = enabled
    config.use_instance = use_instance and config.event_id is not None
    config.updated_by = user
    config.save()
    after = {"enabled": config.enabled, "settings": config.settings, "features": config.features,
             "use_instance": config.use_instance}
    changes = {k: [before[k], after[k]] for k in after if before[k] != after[k]}
    if changed_secrets:
        changes["secrets"] = ["(unchanged)", f"changed: {', '.join(sorted(changed_secrets))}"]
    log(action="extension.configured", actor=user, target=config, event=config.event, request=request,
        message=f"{spec.name} configuration saved", changes=changes, scope={"extension": spec.key})
    return config


def test_connection(config: ExtensionConfig, *, user=None, request=None) -> ConnectionResult:
    spec = config.spec
    if spec is None or spec.test_connection is None:
        result = ConnectionResult(False, "This extension has no connection test.")
    else:
        try:
            result = spec.test_connection(config)
        except Exception as exc:  # noqa: BLE001 - the test reports any failure to the operator
            result = ConnectionResult(False, f"{type(exc).__name__}: {exc}")
    config.health = ExtensionConfig.Health.OK if result.ok else ExtensionConfig.Health.ERROR
    config.last_check_at = timezone.now()
    config.last_error = "" if result.ok else result.message[:2000]
    if config.is_saved:
        config.save(update_fields=["health", "last_check_at", "last_error"])
        write_log(config, "info" if result.ok else "error", f"Connection test: {result.message or 'OK'}",
                  **dict(result.details))
        log(action="extension.tested", actor=user, target=config, event=config.event, request=request,
            message=f"Connection test {'passed' if result.ok else 'failed'}", scope={"extension": config.extension})
    return result


def regenerate_webhook_secret(config: ExtensionConfig, *, user=None, request=None) -> str:
    raw = pysecrets.token_urlsafe(32)
    config.webhook_secret_encrypted = crypto.encrypt(raw)
    config.save(update_fields=["webhook_secret_encrypted"])
    log(action="extension.webhook_secret", actor=user, target=config, event=config.event, request=request,
        message="Inbound webhook secret regenerated", scope={"extension": config.extension})
    return raw


@transaction.atomic
def disconnect(config: ExtensionConfig, *, user=None, request=None) -> None:
    """Disconnect & purge: let the extension delete imported data, then drop the configuration."""
    spec = config.spec
    if spec is not None and spec.purge is not None:
        spec.purge(config)
    log(action="extension.disconnected", actor=user, target=config, event=config.event, request=request,
        message=f"{spec.name if spec else config.extension} disconnected and purged",
        scope={"extension": config.extension})
    config.delete()


# --------------------------------------------------------------------------- signatures

def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not secret or not header:
        return False
    return hmac.compare_digest(sign(secret, body), header.strip())
