# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a venue node receives of the people of an event (ADR-0036): members and instance admins, with their
password hashes and second factors, so they can sign in on site without the uplink."""
from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.core.plugins import SyncModel, SyncSpec


def _users(event: Any) -> Any:
    from .models import User

    return User.objects.filter(Q(memberships__event=event) | Q(is_superuser=True)).distinct()


def spec() -> SyncSpec:
    from .models import RecoveryCode, TOTPDevice, WebAuthnCredential

    return SyncSpec(module="accounts", order=0, models=(
        SyncModel("accounts.User", _users, local_fields=("last_login",), delete_missing=False),
        SyncModel("accounts.TOTPDevice", lambda e: TOTPDevice.objects.filter(user__in=_users(e)),
                  secret_fields=("secret_encrypted",), local_fields=("last_counter", "last_used_at")),
        SyncModel("accounts.WebAuthnCredential", lambda e: WebAuthnCredential.objects.filter(user__in=_users(e)),
                  local_fields=("sign_count", "last_used_at")),
        SyncModel("accounts.RecoveryCode", lambda e: RecoveryCode.objects.filter(user__in=_users(e)),
                  local_fields=("used_at",)),
    ))
