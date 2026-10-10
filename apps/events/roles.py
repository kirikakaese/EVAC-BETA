# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in role templates, created for every new event (editable, not deletable).

Patterns may name permissions of modules that are not installed yet; they simply match nothing until
the module registers them. Two-factor authentication is required by default for every role that may
trigger alarms or manage people (admin, orga, control-room, security).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class RoleTemplate:
    key: str
    name: str
    description: str
    permissions: tuple[str, ...]
    require_2fa: bool
    order: int


BUILTIN_ROLES: tuple[RoleTemplate, ...] = (
    RoleTemplate("admin", str(_("Admin")), str(_("Everything in this event, including roles and deletion.")),
                 ("*",), True, 10),
    RoleTemplate("orga", str(_("Orga")), str(_("Runs the event: settings, content, people, integrations.")),
                 ("*", "!events.delete", "!events.roles"), True, 20),
    RoleTemplate("control-room", str(_("Control room")),
                 str(_("Operates screens, announcements, alarms and incidents during the event.")),
                 ("events.view", "venues.view", "audit.view", "screens.*", "playlists.*", "announcements.*",
                  "evacuation.*", "ops.*", "crowd.*", "notify.*", "access.view", "access.scan"), True, 30),
    RoleTemplate("security", str(_("Security")), str(_("Raises and acknowledges alarms, handles incidents.")),
                 ("events.view", "venues.view", "evacuation.view", "evacuation.trigger", "evacuation.acknowledge",
                  "ops.*", "crowd.view", "announcements.view", "access.view", "access.scan"), True, 40),
    RoleTemplate("helpdesk", str(_("Helpdesk")), str(_("Info desk: lost and found, requests, announcement drafts.")),
                 ("events.view", "venues.view", "helpdesk.*", "announcements.view", "announcements.draft",
                  "access.view", "access.scan"), False, 50),
    RoleTemplate("crew", str(_("Crew")), str(_("Volunteers: own shifts, alarm reception and acknowledgement.")),
                 ("events.view", "venues.view", "crew.view", "crew.self", "announcements.view",
                  "evacuation.acknowledge"), False, 60),
    RoleTemplate("viewer", str(_("Viewer")), str(_("Read-only access to everything visible in the event.")),
                 ("*.view",), False, 70),
)


def ensure_builtin_roles(event) -> None:
    from .models import Role

    existing = set(event.roles.values_list("key", flat=True))
    Role.objects.bulk_create([
        Role(event=event, key=t.key, name=t.name, description=t.description, permissions=list(t.permissions),
             require_2fa=t.require_2fa, builtin=True, order=t.order)
        for t in BUILTIN_ROLES if t.key not in existing
    ])


def template(key: str) -> RoleTemplate | None:
    return next((t for t in BUILTIN_ROLES if t.key == key), None)
