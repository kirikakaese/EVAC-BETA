# SPDX-License-Identifier: AGPL-3.0-or-later
"""Encryption of secrets at rest (extension credentials, TOTP seeds, webhook secrets).

Fernet (AES-128-CBC + HMAC-SHA256) via ``MultiFernet``: the first key in ``EVAC_SECRETS_KEYS`` encrypts,
all keys decrypt, so keys can be rotated (``manage.py evac_rotate_secrets``). Without configured keys a
key is derived from ``SECRET_KEY`` - acceptable for development only; production settings refuse that.
"""
from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class SecretError(Exception):
    pass


def _keys() -> tuple[str, ...]:
    from django.conf import settings

    keys = tuple(k for k in getattr(settings, "EVAC_SECRETS_KEYS", []) if k)
    if keys:
        return keys
    derived = base64.urlsafe_b64encode(hashlib.sha256(("evac-secrets:" + settings.SECRET_KEY).encode()).digest())
    return (derived.decode(),)


@lru_cache(maxsize=4)
def _fernet(keys: tuple[str, ...]) -> MultiFernet:
    return MultiFernet([Fernet(k.encode()) for k in keys])


def fernet() -> MultiFernet:
    return _fernet(_keys())


def encrypt(value: str) -> str:
    if value == "":
        return ""
    return fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretError("secret cannot be decrypted with the configured EVAC_SECRETS_KEYS") from exc


def encrypt_json(value: dict[str, Any]) -> str:
    return encrypt(json.dumps(value, sort_keys=True)) if value else ""


def decrypt_json(token: str) -> dict[str, Any]:
    raw = decrypt(token)
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SecretError("encrypted payload is not an object")
    return data


def rotate(token: str) -> str:
    return fernet().rotate(token.encode()).decode() if token else ""


def generate_key() -> str:
    return Fernet.generate_key().decode()
