# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import AudienceSpec, DataSourceSpec, NavEntry, PermissionSpec, PluginManifest
from apps.core.registry import Registry

manifest = PluginManifest(key="events", name="Events", version="0.1.0", kind="core")


def _event_info(event) -> dict:
    """Data source "event.info" for custom widgets."""
    return {"name": event.name, "slug": event.slug, "state": event.state, "description": event.description,
            "start": event.start_date.isoformat() if event.start_date else None,
            "end": event.end_date.isoformat() if event.end_date else None, "timezone": event.timezone,
            "venues": [{"name": v.name} for v in event.venues.all()]}


def _role_choices(event) -> list[tuple[str, str]]:
    return [(str(pk), name) for pk, name in event.roles.order_by("order", "name").values_list("pk", "name")]


def _role_members(event, ids: set[str]):
    """Audience "roles": active members who hold one of these roles (in any scope)."""
    from .models import RoleAssignment

    return {a.membership.user for a in RoleAssignment.objects.filter(
        membership__event=event, role_id__in=ids, membership__user__is_active=True).select_related("membership__user")}


def register(r: Registry) -> None:
    r.audience(AudienceSpec(key="roles", title=str(_("Role")), choices=_role_choices, members=_role_members,
                            order=10))
    r.data_source(DataSourceSpec(key="event.info", name=str(_("Event details")), fetch=_event_info,
                                 description=str(_("Name, dates, state, description and venues of the event."))))
    r.permissions_([
        PermissionSpec("events.view", str(_("See the event"))),
        PermissionSpec("events.manage", str(_("Edit event details, branding and lifecycle"))),
        PermissionSpec("events.delete", str(_("Delete or archive the event")), sensitive=True),
        PermissionSpec("events.members", str(_("Invite members and assign existing roles"))),
        PermissionSpec("events.roles", str(_("Create and edit roles and their permissions")), sensitive=True),
        PermissionSpec("tokens.manage", str(_("Create API tokens bound to the event"))),
    ])
    r.nav(NavEntry(module="core", label=str(_("Overview")), url_name="portal:event_dashboard",
                   permission="events.view", section="event", order=0, active=("portal:event_dashboard",)))
    r.nav(NavEntry(module="core", label=str(_("Members")), url_name="portal:members", permission="events.members",
                   section="settings", order=20, active=("portal:member*", "portal:invit*")))
    r.nav(NavEntry(module="core", label=str(_("Roles")), url_name="portal:roles", permission="events.members",
                   section="settings", order=25, active=("portal:role*",)))
    r.nav(NavEntry(module="core", label=str(_("Event settings")), url_name="portal:event_settings",
                   permission="events.manage", section="settings", order=10,
                   active=("portal:event_settings", "portal:event_lifecycle", "portal:event_clone",
                           "portal:event_export", "portal:settings_ns")))
    r.nav(NavEntry(module="core", label=str(_("Modules")), url_name="portal:event_modules",
                   permission="modules.manage", section="settings", order=30, active=("portal:event_modules",)))
    r.nav(NavEntry(module="extensions", label=str(_("Extensions")), url_name="extensions:event_index",
                   permission="extensions.manage", section="settings", order=40, active=("extensions:event_*",)))
    r.nav(NavEntry(module="core", label=str(_("API tokens")), url_name="portal:event_tokens",
                   permission="tokens.manage", section="settings", order=50, active=("portal:event_tokens",)))
    r.nav(NavEntry(module="core", label=str(_("Audit log")), url_name="portal:audit", permission="audit.view",
                   section="settings", order=60, active=("portal:audit*",)))
