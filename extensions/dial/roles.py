# SPDX-License-Identifier: AGPL-3.0-or-later
"""DIAL event roles -> EVAC roles (roadmap 4.5). A manual mapping table; a person reviews the proposals and assigns,
nothing is granted automatically (no privilege escalation through DIAL).

DIAL's member list gives usernames, not e-mail addresses, so EVAC suggests the EVAC member whose e-mail local part
or display name equals the DIAL username; the person checks and corrects every row before assigning.
"""
from __future__ import annotations

from typing import Any

from django import forms
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core.audit import log

from .client import Client
from .models import RoleMapping

DIAL_ROLES = [("user", gettext_lazy("User")), ("helpdesk", gettext_lazy("Helpdesk")),
              ("orga", gettext_lazy("Orga / moderator")), ("admin", gettext_lazy("Event admin"))]


class MappingForm(forms.Form):
    def __init__(self, *args: Any, config: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        from apps.events.models import Role

        current = {m.dial_role: m.role_id for m in RoleMapping.objects.filter(config=config)}
        choices = [("", _("— no EVAC role —"))] + [(str(r.pk), r.name) for r in
                                                    Role.objects.filter(event=config.event).order_by("name")]
        for key, label in DIAL_ROLES:
            self.fields[f"role_{key}"] = forms.ChoiceField(label=_("DIAL role “%(r)s”") % {"r": label},
                                                           choices=choices, required=False,
                                                           initial=str(current.get(key) or ""))


def save_mapping(config: Any, data: dict[str, Any], *, actor: Any, request: Any = None) -> None:
    from apps.events.models import Role

    before = {m.dial_role: m.role.key for m in RoleMapping.objects.filter(config=config).select_related("role")}
    with transaction.atomic():
        for key, _label in DIAL_ROLES:
            value = data.get(f"role_{key}") or ""
            if not value:
                RoleMapping.objects.filter(config=config, dial_role=key).delete()
                continue
            role = Role.objects.get(pk=value, event=config.event)
            RoleMapping.objects.update_or_create(config=config, dial_role=key, defaults={"role": role})
    after = {m.dial_role: m.role.key for m in RoleMapping.objects.filter(config=config).select_related("role")}
    log(action="dial.role_mapping", actor=actor, event=config.event, request=request,
        message="DIAL role mapping changed", changes={"mapping": [before, after]})


def fetch_members(config: Any) -> list[dict[str, Any]]:
    """``GET events/<slug>/members/`` (needs a helpdesk or orga token with ``events:read``)."""
    client = Client.for_config(config)
    data = client.get(f"events/{client.event}/members/")
    items = data if isinstance(data, list) else (data or {}).get("results") or []
    return [{"user": str(m.get("user") or ""), "role": str(m.get("role") or ""), "groups": m.get("groups") or []}
            for m in items if isinstance(m, dict) and m.get("user")]


def member_choices(event: Any) -> list[tuple[str, str]]:
    from apps.events.models import Membership

    return [(str(m.user.pk), f"{m.user.display_name or m.user.email} <{m.user.email}>")
            for m in Membership.objects.filter(event=event).select_related("user").order_by("user__email")
            if m.user.is_active]


def _suggest(username: str, users: list[Any]) -> Any:
    name = username.strip().lower()
    for u in users:
        if u.email.split("@", 1)[0].lower() == name or (u.display_name or "").strip().lower() == name:
            return u
    return None


def proposals(config: Any, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from apps.events.models import Membership, RoleAssignment

    mapping = {m.dial_role: m.role for m in RoleMapping.objects.filter(config=config).select_related("role")}
    users = [m.user for m in Membership.objects.filter(event=config.event).select_related("user") if m.user.is_active]
    out = []
    for i, m in enumerate(members):
        role = mapping.get(m["role"])
        if role is None:
            continue
        user = _suggest(m["user"], users)
        has = user is not None and RoleAssignment.objects.filter(membership__event=config.event,
                                                                 membership__user=user, role=role,
                                                                 scope_kind="").exists()
        out.append({"index": i, "dial_user": m["user"], "dial_role": m["role"], "role": role, "user": user,
                    "has": has})
    return out


def apply(config: Any, rows: list[dict[str, Any]], post: Any, *, actor: Any, request: Any = None) -> int:
    """Assign the ticked rows (``pick_<i>``) to the EVAC member chosen per row (``user_<i>``)."""
    from apps.accounts.models import User
    from apps.events import services
    from apps.events.models import Membership

    members = {str(m.user_id) for m in Membership.objects.filter(event=config.event)}
    n = 0
    for row in rows:
        i = row["index"]
        if not post.get(f"pick_{i}"):
            continue
        uid = post.get(f"user_{i}") or ""
        if uid not in members:  # only people who already are members of the event
            continue
        user = User.objects.get(pk=uid)
        services.assign_role(config.event, user, row["role"], actor=actor, request=request)
        log(action="dial.role_assigned", actor=actor, event=config.event, request=request, target=user,
            message=f"{user.email} got {row['role'].name} (DIAL {row['dial_role']} {row['dial_user']})")
        n += 1
    return n
