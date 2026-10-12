# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    AudienceSpec,
    DataSourceSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    SetupCheckSpec,
    SetupResult,
)
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


def _team_check(event, request):
    """Setup checklist: someone besides the creator is a member or invited."""
    from django.utils import timezone

    if event.memberships.count() > 1 or event.invitations.filter(accepted_at__isnull=True,
                                                                 expires_at__gt=timezone.now()).exists():
        return "done"
    return "todo"


def _two_factor_check(event, request):
    """Setup checklist: everyone holding a role with alarm-relevant (sensitive) permissions has two-factor sign-in;
    those permissions only work in a two-factor verified session."""
    from django.contrib.auth import get_user_model
    from django.urls import reverse
    from django.utils.translation import ngettext

    roles = [r.pk for r in event.roles.all() if r.grants_sensitive]
    if not roles:
        return None
    missing = set(get_user_model().objects.filter(
        is_active=True, memberships__event=event, memberships__assignments__role__in=roles,
    ).exclude(totp_devices__confirmed=True).filter(webauthn_credentials__isnull=True).values_list("pk", flat=True))
    if not missing:
        return "done"
    detail = ngettext("%(n)s person with alarm permissions has no two-factor sign-in yet.",
                      "%(n)s people with alarm permissions have no two-factor sign-in yet.", len(missing)) % {
        "n": len(missing)}
    me = getattr(getattr(request, "user", None), "pk", None)
    if me in missing:
        return SetupResult("todo", detail=detail + " " + str(_("That includes you.")), url=reverse("accounts:security"))
    return SetupResult("todo", detail=detail)


def register(r: Registry) -> None:
    from . import sync as node_sync

    r.sync(node_sync.spec())
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
    r.setup_check(SetupCheckSpec(
        key="team", label=str(_("Invite your team")), check=_team_check, url_name="portal:members", order=60,
        help=str(_("Invite people by e-mail and give them a role."))))
    r.setup_check(SetupCheckSpec(
        key="two_factor", label=str(_("Two-factor sign-in for everyone with alarm permissions")),
        check=_two_factor_check, url_name="portal:members", order=70,
        help=str(_("Alarm-relevant permissions only work in a session confirmed with a second factor."))))
    r.nav(NavEntry(module="core", label=str(_("Overview")), url_name="portal:event_dashboard",
                   permission="events.view", section="event", order=0, active=("portal:event_dashboard",)))
    r.nav(NavEntry(module="core", label=str(_("Members")), url_name="portal:members", permission="events.members",
                   section="settings", order=20, active=("portal:member*", "portal:invit*")))
    r.nav(NavEntry(module="core", label=str(_("Roles")), url_name="portal:roles", permission="events.members",
                   section="settings", order=25, active=("portal:role*",)))
    r.nav(NavEntry(module="core", label=str(_("Event settings")), url_name="portal:event_settings",
                   permission="events.manage", section="settings", order=10,
                   active=("portal:event_settings", "portal:event_lifecycle", "portal:event_clone",
                           "portal:event_export", "portal:settings_ns", "portal:event_setup*",
                           "portal:setup_checklist")))
    r.nav(NavEntry(module="core", label=str(_("Modules")), url_name="portal:event_modules",
                   permission="modules.manage", section="settings", order=30, active=("portal:event_modules",)))
    r.nav(NavEntry(module="extensions", label=str(_("Extensions")), url_name="extensions:event_index",
                   permission="extensions.manage", section="settings", order=40, active=("extensions:event_*",)))
    r.nav(NavEntry(module="core", label=str(_("API tokens")), url_name="portal:event_tokens",
                   permission="tokens.manage", section="settings", order=50, active=("portal:event_tokens",)))
    r.nav(NavEntry(module="core", label=str(_("Audit log")), url_name="portal:audit", permission="audit.view",
                   section="settings", order=60, active=("portal:audit*",)))
