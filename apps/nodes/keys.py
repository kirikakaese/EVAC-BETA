# SPDX-License-Identifier: AGPL-3.0-or-later
"""Node identity keys (ADR-0002, ADR-0036).

A node has two key pairs, generated on the node at enrolment: Ed25519 signs every request to central, X25519
receives secrets (central seals a secret for the node: ephemeral X25519, HKDF-SHA256, AES-256-GCM).
"""
from __future__ import annotations

import base64
import hashlib
import os
import time

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

#: requests older or newer than this are refused (replay window)
MAX_SKEW = 300
SEALED = "sealed:"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _raw(key: Ed25519PrivateKey | X25519PrivateKey) -> bytes:
    return key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())


def _pub(key: Ed25519PrivateKey | X25519PrivateKey) -> str:
    return b64(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def generate() -> dict[str, str]:
    """New identity: ``{"sign_private", "sign_public", "box_private", "box_public"}`` (base64url)."""
    sign, box = Ed25519PrivateKey.generate(), X25519PrivateKey.generate()
    return {"sign_private": b64(_raw(sign)), "sign_public": _pub(sign),
            "box_private": b64(_raw(box)), "box_public": _pub(box)}


def message(method: str, path: str, timestamp: str, body: bytes) -> bytes:
    return f"{method.upper()}\n{path}\n{timestamp}\n{hashlib.sha256(body).hexdigest()}".encode()


def sign_request(sign_private: str, method: str, path: str, body: bytes, now: float | None = None) -> dict[str, str]:
    ts = str(int(now if now is not None else time.time()))
    sig = Ed25519PrivateKey.from_private_bytes(unb64(sign_private)).sign(message(method, path, ts, body))
    return {"X-EVAC-Node-Timestamp": ts, "X-EVAC-Node-Signature": b64(sig)}


def verify_request(sign_public: str, method: str, path: str, body: bytes, timestamp: str, signature: str,
                   now: float | None = None) -> bool:
    try:
        if abs((now if now is not None else time.time()) - int(timestamp)) > MAX_SKEW:
            return False
        Ed25519PublicKey.from_public_bytes(unb64(sign_public)).verify(unb64(signature),
                                                                      message(method, path, timestamp, body))
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def _kdf(shared: bytes, eph: bytes, recipient: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=eph + recipient, info=b"evac-node-seal").derive(shared)


def seal(box_public: str, plaintext: str) -> str:
    """Encrypt ``plaintext`` so only the node holding ``box_public``'s private key can read it."""
    recipient = unb64(box_public)
    eph = X25519PrivateKey.generate()
    eph_pub = eph.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key = _kdf(eph.exchange(X25519PublicKey.from_public_bytes(recipient)), eph_pub, recipient)
    nonce = os.urandom(12)
    return SEALED + b64(eph_pub + nonce + AESGCM(key).encrypt(nonce, plaintext.encode(), None))


def open_sealed(box_private: str, sealed: str) -> str:
    if not sealed.startswith(SEALED):
        raise ValueError("not sealed")
    raw = unb64(sealed[len(SEALED):])
    eph_pub, nonce, ct = raw[:32], raw[32:44], raw[44:]
    priv = X25519PrivateKey.from_private_bytes(unb64(box_private))
    recipient = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key = _kdf(priv.exchange(X25519PublicKey.from_public_bytes(eph_pub)), eph_pub, recipient)
    try:
        return AESGCM(key).decrypt(nonce, ct, None).decode()
    except InvalidTag as err:
        raise ValueError("sealed value does not open with this node's key") from err
