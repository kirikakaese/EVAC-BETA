# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory

from apps.accounts.twofactor import SESSION_KEY
from apps.events import rbac, services
from apps.events.roles import BUILTIN_ROLES
from apps.venues.models import Room, Zone


def req(user, two_factor=False):
    r = RequestFactory().get("/")
    r.user = user
    r.session = {SESSION_KEY: "x"} if two_factor else {}
    return r


@pytest.mark.django_db
def test_builtin_roles_created(event):
    assert set(event.roles.values_list("key", flat=True)) == {t.key for t in BUILTIN_ROLES}
    orga = event.roles.get(key="orga")
    assert "events.manage" in orga.expanded() and "events.delete" not in orga.expanded()
    assert event.roles.get(key="admin").require_2fa
    assert not event.roles.get(key="viewer").require_2fa
    assert event.roles.get(key="viewer").expanded() >= {"events.view", "venues.view", "audit.view"}


@pytest.mark.django_db
def test_creator_is_admin(event, admin, user):
    assert event.memberships.filter(user=admin).exists()
    assert not rbac.is_member(user, event)


@pytest.mark.django_db
def test_orga_role_requires_2fa(event, orga):
    assert not rbac.has_perm(orga, event, "events.manage", request=req(orga))
    assert rbac.effective(orga, event, request=req(orga)).blocked_roles == ["Orga"]
    assert rbac.has_perm(orga, event, "events.manage", request=req(orga, True))
    assert not rbac.has_perm(orga, event, "events.delete", request=req(orga, True))


@pytest.mark.django_db
def test_superuser_sensitive_needs_2fa(event, admin):
    assert rbac.has_perm(admin, event, "events.manage", request=req(admin))
    assert not rbac.has_perm(admin, event, "events.roles", request=req(admin))
    assert rbac.has_perm(admin, event, "events.roles", request=req(admin, True))


@pytest.mark.django_db
def test_scoped_assignment(event, user, venue, role):
    north = Zone.objects.get(name="North")
    services.assign_role(event, user, role("viewer"), scope_kind="zone", scope_id=str(north.pk))
    room_a, room_b = Room.objects.get(name="Hall A"), Room.objects.get(name="Hall B")
    r = req(user)
    assert rbac.has_perm(user, event, "venues.view", obj=room_a, request=r)
    assert not rbac.has_perm(user, event, "venues.view", obj=room_b, request=req(user))
    assert not rbac.has_perm(user, event, "venues.view", request=req(user))
    assert rbac.has_any(user, event, "venues.view", request=req(user))


@pytest.mark.django_db
def test_assign_validates_scope_and_event(event, user, role, admin):
    with pytest.raises(ValidationError):
        services.assign_role(event, user, role("viewer"), scope_kind="zone", scope_id="not-a-zone")
    with pytest.raises(ValidationError):
        services.assign_role(event, user, role("viewer"), scope_kind="planet", scope_id="x")
    other_event = services.create_event(name="Other", user=admin)
    with pytest.raises(ValidationError):
        services.assign_role(event, user, other_event.roles.get(key="viewer"))


@pytest.mark.django_db
def test_last_admin_guard(event, admin, user, role):
    ra = event.memberships.get(user=admin).assignments.get(role__key="admin")
    with pytest.raises(ValidationError):
        services.unassign_role(ra, actor=admin)
    with pytest.raises(ValidationError):
        services.remove_member(event.memberships.get(user=admin), actor=admin)
    services.assign_role(event, user, role("admin"))
    services.unassign_role(ra, actor=admin)


@pytest.mark.django_db
def test_require_raises(event, user):
    with pytest.raises(PermissionDenied):
        rbac.require(req(user), event, "events.view")


@pytest.mark.django_db
def test_inactive_user_has_no_access(event, member):
    member.is_active = False
    assert not rbac.has_perm(member, event, "events.view")


@pytest.mark.django_db
def test_token_bound_to_other_event(event, admin, member):
    from apps.accounts.models import ServiceToken

    other = services.create_event(name="Other", user=admin)
    tok, _ = ServiceToken.issue(name="t", owner=member, event=other)
    r = req(member)
    r.service_token = tok
    assert not rbac.has_perm(member, event, "events.view", request=r)
