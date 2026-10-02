# SPDX-License-Identifier: AGPL-3.0-or-later
"""GDPR export (Art. 15/20) and erasure (Art. 17) of a user account.

Erasure anonymises the account row (so foreign keys and the audit trail stay consistent), deletes
tokens, second factors, memberships and notifications. Audit log rows are immutable by design and keep
the actor description they were written with; they are covered by the audit retention policy
(see docs/SECURITY.md, "Privacy").
"""
from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from apps.core.audit import log
from apps.core.models import AuditLog

from .models import RecoveryCode, User


def export_user(user: User) -> dict:
    return {
        "account": {"id": str(user.pk), "email": user.email, "display_name": user.display_name,
                    "date_joined": user.date_joined.isoformat(), "email_verified": user.email_verified,
                    "is_superuser": user.is_superuser, "sso_linked": bool(user.oidc_subject)},
        "memberships": [
            {"event": m.event.slug, "joined": m.created_at.isoformat(),
             "roles": [str(a) for a in m.assignments.select_related("role")]}
            for m in user.memberships.select_related("event")
        ],
        "service_tokens": [{"name": t.name, "prefix": t.token_prefix, "scopes": t.scopes,
                            "created_at": t.created_at.isoformat(),
                            "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None}
                           for t in user.service_tokens.all()],
        "second_factors": [{"type": "totp", "name": d.name, "created_at": d.created_at.isoformat()}
                           for d in user.totp_devices.filter(confirmed=True)]
        + [{"type": "webauthn", "name": c.name, "created_at": c.created_at.isoformat()}
           for c in user.webauthn_credentials.all()],
        "notifications": [{"title": n.title, "created_at": n.created_at.isoformat()}
                          for n in user.notifications.all()[:500]],
        "audit_log_actions": [{"at": a.created_at.isoformat(), "action": a.action, "event": a.event_repr,
                               "message": a.message} for a in AuditLog.objects.filter(actor_id=user.pk)[:1000]],
    }


@transaction.atomic
def delete_user(user: User, *, request=None) -> None:
    from apps.events.models import RoleAssignment

    if user.is_superuser and User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk).count() == 0:
        raise ValidationError(_("You are the last instance admin. Make someone else admin first."))
    for ra in RoleAssignment.objects.filter(membership__user=user, role__key="admin", scope_kind=""):
        others = RoleAssignment.objects.filter(membership__event=ra.membership.event_id, role__key="admin",
                                               scope_kind="").exclude(membership__user=user)
        if not others.exists():
            raise ValidationError(_("You are the only admin of %(event)s. Hand over the admin role first.")
                                  % {"event": ra.membership.event.name})
    log(action="account.deleted", actor=user, target=user, request=request, message="Account erased on request")
    user.service_tokens.all().delete()
    user.totp_devices.all().delete()
    user.webauthn_credentials.all().delete()
    RecoveryCode.objects.filter(user=user).delete()
    user.memberships.all().delete()
    user.notifications.all().delete()
    user.email = f"deleted-{uuid.uuid4().hex[:12]}@invalid.invalid"
    user.display_name = _("Deleted user")
    user.oidc_subject = ""
    user.is_active = False
    user.is_superuser = False
    user.is_staff = False
    user.set_unusable_password()
    user.save()
