# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event services: creation, membership, role assignment, invitations, clone, export and import.

Always go through these functions (not the ORM) for state changes: they write the audit log and emit
webhook events.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from apps.core import modules
from apps.core.audit import log
from apps.core.models import EventModuleState, SettingValue
from apps.core.registry import registry
from apps.core.webhooks import emit

from .models import Event, Invitation, Membership, Role, RoleAssignment
from .roles import ensure_builtin_roles

EXPORT_VERSION = 1


def unique_slug(base: str) -> str:
    base = slugify(base)[:40] or "event"
    slug, n = base, 1
    while Event.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


@transaction.atomic
def create_event(*, name: str, slug: str = "", user=None, request=None, admin_role: bool = True, **fields) -> Event:
    event = Event(name=name, slug=slug or unique_slug(name), created_by=user, **fields)
    event.full_clean()
    event.save()
    ensure_builtin_roles(event)
    if user is not None and admin_role:
        assign_role(event, user, event.roles.get(key="admin"), actor=user, request=request)
    log(action="event.created", actor=user, target=event, event=event, request=request, message=f"Event {name} created")
    emit("event.created", {"slug": event.slug, "name": event.name}, event=event)
    return event


def ensure_member(event, user, *, actor=None, request=None) -> Membership:
    m, created = Membership.objects.get_or_create(event=event, user=user, defaults={"added_by": actor})
    if created:
        log(action="member.added", actor=actor, target=m, event=event, request=request,
            message=f"{user.email} joined", scope={"user": str(user.pk)})
        emit("member.added", {"user": user.email}, event=event)
    return m


def assign_role(event, user, role: Role, *, scope_kind: str = "", scope_id: str = "", scope_label: str = "",
                actor=None, request=None) -> RoleAssignment:
    if role.event_id != event.pk:
        raise ValidationError(_("This role belongs to another event."))
    if scope_kind:
        kinds = registry.ensure_loaded().scope_kinds
        if scope_kind not in kinds:
            raise ValidationError(_("Unknown scope type."))
        valid = {str(k): str(v) for k, v in kinds[scope_kind].choices(event)}
        if str(scope_id) not in valid:
            raise ValidationError(_("This scope does not exist in the event."))
        scope_label = scope_label or valid[str(scope_id)]
    m = ensure_member(event, user, actor=actor, request=request)
    ra, created = RoleAssignment.objects.get_or_create(
        membership=m, role=role, scope_kind=scope_kind, scope_id=str(scope_id), defaults={"scope_label": scope_label})
    if created:
        log(action="role.assigned", actor=actor, target=m, event=event, request=request,
            message=f"{user.email} got role {role.name}" + (f" in {scope_kind} {scope_label}" if scope_kind else ""),
            scope={"user": str(user.pk), "role": role.key, "scope_kind": scope_kind, "scope_id": str(scope_id)})
    return ra


def unassign_role(ra: RoleAssignment, *, actor=None, request=None) -> None:
    m = ra.membership
    _guard_last_admin(m.event, removing=[ra])
    log(action="role.unassigned", actor=actor, target=m, event=m.event, request=request,
        message=f"{m.user.email} lost role {ra.role.name}",
        scope={"user": str(m.user_id), "role": ra.role.key, "scope_kind": ra.scope_kind, "scope_id": ra.scope_id})
    ra.delete()


def remove_member(m: Membership, *, actor=None, request=None) -> None:
    _guard_last_admin(m.event, removing=list(m.assignments.all()))
    event, email = m.event, m.user.email
    log(action="member.removed", actor=actor, target=m, event=event, request=request, message=f"{email} removed")
    m.delete()
    emit("member.removed", {"user": email}, event=event)


def _guard_last_admin(event, removing: list[RoleAssignment]) -> None:
    """Never leave an event without an unscoped admin (instance admins can always recover, but be safe)."""
    admins = RoleAssignment.objects.filter(membership__event=event, role__key="admin", scope_kind="")
    remaining = admins.exclude(pk__in=[r.pk for r in removing])
    if admins.exists() and not remaining.exists():
        raise ValidationError(_("An event needs at least one admin. Make someone else admin first."))


def save_role(role: Role, *, actor=None, request=None, before: dict | None = None) -> Role:
    unknown = [p for p in role.permissions if not registry.expand([p.lstrip("!")])]
    role.full_clean()
    role.save()
    log(action="role.saved", actor=actor, target=role, event=role.event, request=request,
        message=f"Role {role.name} saved", changes={k: [(before or {}).get(k), getattr(role, k)]
                                                    for k in ("name", "permissions", "require_2fa")
                                                    if (before or {}).get(k) != getattr(role, k)},
        scope={"unmatched_patterns": unknown} if unknown else None)
    return role


# --------------------------------------------------------------------------- invitations

def invite(event, email: str, role: Role, *, actor=None, request=None, scope_kind="", scope_id="",
           scope_label="", send=True) -> tuple[Invitation, str]:
    inv, raw = Invitation.issue(event=event, email=email, role=role, created_by=actor, scope_kind=scope_kind,
                                scope_id=scope_id, scope_label=scope_label)
    url = f"{settings.EVAC_PUBLIC_URL}/invite/{raw}/"
    if send:
        send_mail(
            subject=_("Invitation to %(event)s on EVAC") % {"event": event.name},
            message=_("You have been invited to join %(event)s as %(role)s.\n\nAccept the invitation: %(url)s\n\n"
                      "The link is valid until %(until)s.") % {"event": event.name, "role": role.name, "url": url,
                                                             "until": inv.expires_at.strftime("%Y-%m-%d %H:%M UTC")},
            from_email=None, recipient_list=[inv.email], fail_silently=True,
        )
    log(action="member.invited", actor=actor, target=inv, event=event, request=request,
        message=f"{inv.email} invited as {role.name}")
    return inv, url


def lookup_invitation(raw: str) -> Invitation | None:
    if not raw or len(raw) > 128:
        return None
    inv = Invitation.objects.select_related("event", "role").filter(token_hash=Invitation.hash_token(raw)).first()
    return inv if inv is not None and inv.is_valid else None


@transaction.atomic
def accept_invitation(inv: Invitation, user, *, request=None) -> Membership:
    if not inv.is_valid:
        raise ValidationError(_("This invitation is no longer valid."))
    assign_role(inv.event, user, inv.role, scope_kind=inv.scope_kind, scope_id=inv.scope_id,
                scope_label=inv.scope_label, actor=user, request=request)
    inv.accepted_at = timezone.now()
    inv.accepted_by = user
    inv.save(update_fields=["accepted_at", "accepted_by"])
    if user.email.lower() == inv.email and not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    log(action="member.invitation_accepted", actor=user, target=inv, event=inv.event, request=request,
        message=f"{user.email} accepted the invitation")
    return Membership.objects.get(event=inv.event, user=user)


# --------------------------------------------------------------------------- scheduled transitions

def apply_due_transitions(now: dt.datetime | None = None) -> int:
    from .models import ScheduledTransition

    now = now or timezone.now()
    applied = 0
    due = ScheduledTransition.objects.filter(applied_at__isnull=True, at__lte=now, error="").select_related("event")
    for st in due:
        event = st.event
        with transaction.atomic():
            if event.state == st.target_state:
                st.applied_at = now
            elif event.can_transition(st.target_state):
                event.transition(st.target_state, user=None, reason=f"Scheduled transition to {st.target_state}")
                st.applied_at = now
                applied += 1
            else:
                st.error = f"cannot go from {event.state} to {st.target_state}"
            st.save(update_fields=["applied_at", "error"])
    return applied


# --------------------------------------------------------------------------- clone / export / import

EVENT_FIELDS = ("name", "description", "timezone", "start_date", "end_date", "primary_color", "accent_color",
                "default_theme")


@transaction.atomic
def clone_event(src: Event, *, name: str, slug: str = "", with_content: bool = False, user=None,
                request=None) -> Event:
    """Copy an event's structure (settings, roles, modules, venues, extension settings) and optionally its
    content (members and everything plugins consider content). Secrets are never copied."""
    fields = {f: getattr(src, f) for f in EVENT_FIELDS if f != "name"}
    dst = create_event(name=name, slug=slug, user=user, request=request, admin_role=False, **fields)
    dst.logo = src.logo
    dst.save(update_fields=["logo"])
    dst.venues.set(src.venues.all())
    for role in src.roles.all():
        Role.objects.update_or_create(event=dst, key=role.key, defaults={
            "name": role.name, "description": role.description, "permissions": role.permissions,
            "require_2fa": role.require_2fa, "builtin": role.builtin, "order": role.order})
    for ms in src.module_states.all():
        EventModuleState.objects.create(event=dst, key=ms.key, enabled=ms.enabled, updated_by=user)
    for sv in SettingValue.objects.filter(level="event", scope_id=str(src.pk)):
        SettingValue.objects.create(namespace=sv.namespace, level="event", scope_id=str(dst.pk), values=sv.values,
                                    updated_by=user)
    if with_content:
        for m in src.memberships.prefetch_related("assignments__role"):
            for ra in m.assignments.all():
                assign_role(dst, m.user, dst.roles.get(key=ra.role.key), scope_kind=ra.scope_kind,
                            scope_id=ra.scope_id, scope_label=ra.scope_label, actor=user)
    if user is not None and not dst.memberships.filter(user=user).exists():
        assign_role(dst, user, dst.roles.get(key="admin"), actor=user)
    for hook in registry.hooks():
        if hook.clone is not None:
            hook.clone(src, dst, with_content)
    log(action="event.cloned", actor=user, target=dst, event=dst, request=request,
        message=f"Cloned from {src.slug} ({'with' if with_content else 'without'} content)")
    return dst


def export_event(event: Event) -> dict[str, Any]:
    data: dict[str, Any] = {
        "evac_export": EXPORT_VERSION,
        "exported_at": timezone.now().isoformat(),
        "event": {"slug": event.slug, "state": event.state,
                  **{f: (getattr(event, f).isoformat() if hasattr(getattr(event, f), "isoformat")
                         else getattr(event, f)) for f in EVENT_FIELDS}},
        "roles": [{"key": r.key, "name": r.name, "description": r.description, "permissions": r.permissions,
                   "require_2fa": r.require_2fa, "builtin": r.builtin, "order": r.order} for r in event.roles.all()],
        "members": [
            {"email": m.user.email, "roles": [{"role": ra.role.key, "scope_kind": ra.scope_kind,
                                               "scope_id": ra.scope_id, "scope_label": ra.scope_label}
                                              for ra in m.assignments.all()]}
            for m in event.memberships.select_related("user").prefetch_related("assignments__role")
        ],
        "modules": {ms.key: ms.enabled for ms in event.module_states.all()},
        "settings": {sv.namespace: sv.values for sv in SettingValue.objects.filter(level="event",
                                                                                    scope_id=str(event.pk))},
        "plugins": {},
    }
    for hook in registry.hooks():
        if hook.export is not None:
            data["plugins"][hook.module] = hook.export(event)
    return data


@transaction.atomic
def import_event(data: dict[str, Any], *, slug: str = "", name: str = "", user=None,
                 request=None) -> tuple[Event, list[str]]:
    """Create a new event from :func:`export_event` output. Returns ``(event, report lines)``."""
    from django.contrib.auth import get_user_model

    if not isinstance(data, dict) or data.get("evac_export") != EXPORT_VERSION:
        raise ValidationError(_("This is not an EVAC event export (or from an unsupported version)."))
    report: list[str] = []
    src = data.get("event") or {}
    fields = {f: src.get(f) for f in EVENT_FIELDS if f in src and f != "name" and src.get(f) is not None}
    for f in ("start_date", "end_date"):
        if f in fields:
            fields[f] = dt.date.fromisoformat(fields[f])
    event = create_event(name=name or src.get("name") or "Imported event",
                         slug=slug or unique_slug(src.get("slug", "")), user=user, request=request, admin_role=False,
                         **fields)
    for r in data.get("roles", []):
        Role.objects.update_or_create(event=event, key=r["key"], defaults={
            "name": r.get("name", r["key"]), "description": r.get("description", ""),
            "permissions": list(r.get("permissions", [])), "require_2fa": bool(r.get("require_2fa")),
            "builtin": bool(r.get("builtin")), "order": int(r.get("order", 100))})
    for key, enabled in (data.get("modules") or {}).items():
        if key in registry.ensure_loaded().modules:
            modules.set_event(event, key, bool(enabled), user=user)
    for ns, values in (data.get("settings") or {}).items():
        if ns in registry.settings_namespaces:
            SettingValue.objects.update_or_create(namespace=ns, level="event", scope_id=str(event.pk),
                                                  defaults={"values": values, "updated_by": user})
    for hook in registry.hooks():
        if hook.import_ is not None and hook.module in (data.get("plugins") or {}):
            hook.import_(event, data["plugins"][hook.module], user)
    User = get_user_model()
    for m in data.get("members", []):
        u = User.objects.filter(email__iexact=m.get("email", "")).first()
        if u is None:
            report.append(_("Skipped unknown user %(email)s (invite them).") % {"email": m.get("email")})
            continue
        for ra in m.get("roles", []):
            role = event.roles.filter(key=ra.get("role")).first()
            if role is None:
                continue
            try:
                assign_role(event, u, role, scope_kind=ra.get("scope_kind", ""), scope_id=ra.get("scope_id", ""),
                            actor=user)
            except ValidationError:
                report.append(_("Skipped %(role)s scope for %(email)s (scope not found).")
                              % {"role": role.name, "email": u.email})
    if user is not None and not event.memberships.filter(user=user).exists():
        assign_role(event, user, event.roles.get(key="admin"), actor=user)
    log(action="event.imported", actor=user, target=event, event=event, request=request,
        message=f"Imported from export of {src.get('slug', '?')}")
    return event, report
