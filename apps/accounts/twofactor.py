# SPDX-License-Identifier: AGPL-3.0-or-later
"""Second factors: TOTP (RFC 6238), WebAuthn (security keys / passkeys) and one-time recovery codes.

A session counts as two-factor verified when ``request.session[SESSION_KEY]`` is set; that happens
after a successful second-factor step at login (or right after enrolling the first factor). Sensitive
permissions and roles with ``require_2fa`` only apply in such a session (see apps/events/rbac.py).
"""
from __future__ import annotations

import base64
import io
import secrets
from typing import Any

import pyotp
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.audit import log

from .models import RecoveryCode, TOTPDevice, User, WebAuthnCredential

SESSION_KEY = "evac_2fa_verified_at"
PENDING_KEY = "evac_2fa_pending_user"
PENDING_BACKEND_KEY = "evac_2fa_pending_backend"
PENDING_NEXT_KEY = "evac_2fa_pending_next"
TOTP_ISSUER = "EVAC"
RECOVERY_CODES = 10


def is_verified(request) -> bool:
    return bool(getattr(request, "session", None) and request.session.get(SESSION_KEY))


def mark_verified(request) -> None:
    request.session[SESSION_KEY] = timezone.now().isoformat()


# --------------------------------------------------------------------------- TOTP

def new_totp(user: User, name: str = "Authenticator app") -> TOTPDevice:
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    dev = TOTPDevice(user=user, name=name or "Authenticator app")
    dev.secret = pyotp.random_base32()
    dev.save()
    return dev


def provisioning_uri(dev: TOTPDevice) -> str:
    return pyotp.TOTP(dev.secret).provisioning_uri(name=dev.user.email, issuer_name=TOTP_ISSUER)


def qr_svg(data: str) -> str:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    buf = io.BytesIO()
    img.save(buf)
    # the library names every path "qr-path"; ids must be unique when a page shows several codes (label sheets)
    return buf.getvalue().decode().replace(' id="qr-path"', "")


def _check_totp(dev: TOTPDevice, code: str) -> bool:
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != 6:
        return False
    totp = pyotp.TOTP(dev.secret)
    now = timezone.now().timestamp()
    for drift in (-1, 0, 1):
        counter = int(now // totp.interval) + drift
        if counter <= dev.last_counter:
            continue  # replay of an already used code
        if secrets.compare_digest(totp.generate_otp(counter), code):
            dev.last_counter = counter
            dev.last_used_at = timezone.now()
            dev.save(update_fields=["last_counter", "last_used_at"])
            return True
    return False


def confirm_totp(dev: TOTPDevice, code: str) -> bool:
    if not _check_totp(dev, code):
        return False
    dev.confirmed = True
    dev.save(update_fields=["confirmed"])
    log(action="account.2fa_added", actor=dev.user, target=dev.user, message=f"TOTP device '{dev.name}' added")
    return True


def verify_totp(user: User, code: str) -> bool:
    return any(_check_totp(dev, code) for dev in user.totp_devices.filter(confirmed=True))


# --------------------------------------------------------------------------- recovery codes

def generate_recovery_codes(user: User) -> list[str]:
    codes = ["-".join(secrets.token_hex(3) for _ in range(2)) for _ in range(RECOVERY_CODES)]
    with transaction.atomic():
        RecoveryCode.objects.filter(user=user).delete()
        RecoveryCode.objects.bulk_create(RecoveryCode(user=user, code_hash=RecoveryCode.hash_code(c)) for c in codes)
    log(action="account.recovery_codes", actor=user, target=user, message="Recovery codes regenerated")
    return codes


def use_recovery_code(user: User, code: str) -> bool:
    rc = RecoveryCode.objects.filter(user=user, code_hash=RecoveryCode.hash_code(code or ""),
                                     used_at__isnull=True).first()
    if rc is None:
        return False
    rc.used_at = timezone.now()
    rc.save(update_fields=["used_at"])
    log(action="account.recovery_code_used", actor=user, target=user, message="Recovery code used for login")
    return True


def remaining_recovery_codes(user: User) -> int:
    return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


def remove_all(user: User, actor=None) -> None:
    with transaction.atomic():
        user.totp_devices.all().delete()
        user.webauthn_credentials.all().delete()
        RecoveryCode.objects.filter(user=user).delete()
    log(action="account.2fa_reset", actor=actor or user, target=user, message="All second factors removed")


# --------------------------------------------------------------------------- WebAuthn

def _rp_id(request) -> str:
    if settings.EVAC_WEBAUTHN_RP_ID:
        return settings.EVAC_WEBAUTHN_RP_ID
    return request.get_host().split(":")[0]


def _origin(request) -> str:
    return f"{request.scheme}://{request.get_host()}"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def webauthn_register_options(request, user: User) -> str:
    import webauthn
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    opts = webauthn.generate_registration_options(
        rp_id=_rp_id(request), rp_name=settings.EVAC_WEBAUTHN_RP_NAME,
        user_id=user.pk.bytes, user_name=user.email, user_display_name=str(user),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=b64url_decode(c.credential_id))
                             for c in user.webauthn_credentials.all()],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.DISCOURAGED,
            user_verification=UserVerificationRequirement.PREFERRED),
    )
    request.session["webauthn_reg_challenge"] = b64url(opts.challenge)
    return webauthn.options_to_json(opts)


def webauthn_register_verify(request, user: User, credential: Any, name: str) -> WebAuthnCredential:
    import webauthn

    challenge = request.session.pop("webauthn_reg_challenge", None)
    if not challenge:
        raise ValueError("no registration in progress")
    result = webauthn.verify_registration_response(
        credential=credential, expected_challenge=b64url_decode(challenge),
        expected_rp_id=_rp_id(request), expected_origin=_origin(request))
    cred = WebAuthnCredential.objects.create(
        user=user, name=(name or "Security key")[:60], credential_id=b64url(result.credential_id),
        public_key=b64url(result.credential_public_key), sign_count=result.sign_count,
        transports=(credential.get("response", {}) or {}).get("transports", []) if isinstance(credential, dict) else [],
    )
    log(action="account.2fa_added", actor=user, target=user, message=f"Security key '{cred.name}' added")
    return cred


def webauthn_auth_options(request, user: User) -> str:
    import webauthn
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

    opts = webauthn.generate_authentication_options(
        rp_id=_rp_id(request),
        allow_credentials=[PublicKeyCredentialDescriptor(id=b64url_decode(c.credential_id))
                           for c in user.webauthn_credentials.all()],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    request.session["webauthn_auth_challenge"] = b64url(opts.challenge)
    return webauthn.options_to_json(opts)


def webauthn_auth_verify(request, user: User, credential: Any) -> bool:
    import webauthn

    challenge = request.session.pop("webauthn_auth_challenge", None)
    if not challenge or not isinstance(credential, dict):
        return False
    cred = user.webauthn_credentials.filter(credential_id=str(credential.get("id", ""))).first()
    if cred is None:
        return False
    try:
        result = webauthn.verify_authentication_response(
            credential=credential, expected_challenge=b64url_decode(challenge),
            expected_rp_id=_rp_id(request), expected_origin=_origin(request),
            credential_public_key=b64url_decode(cred.public_key), credential_current_sign_count=cred.sign_count)
    except Exception:  # noqa: BLE001 - any verification error is a failed login
        return False
    cred.sign_count = result.new_sign_count
    cred.last_used_at = timezone.now()
    cred.save(update_fields=["sign_count", "last_used_at"])
    return True
