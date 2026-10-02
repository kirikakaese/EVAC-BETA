# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core import mail

from apps.accounts.models import ServiceToken, User
from apps.core.models import Notification
from apps.events import services
from conftest import login_2fa


@pytest.mark.django_db
def test_profile_and_password(client, user):
    client.force_login(user)
    client.post("/accounts/profile/", {"save_profile": "1", "display_name": "Alice A."})
    user.refresh_from_db()
    assert user.display_name == "Alice A."
    r = client.post("/accounts/profile/", {"change_password": "1", "pw-old_password": "pw-alice-12345",
                                           "pw-new_password1": "a-much-better-pass-42",
                                           "pw-new_password2": "a-much-better-pass-42"})
    assert r.status_code == 302
    user.refresh_from_db()
    assert user.check_password("a-much-better-pass-42")


@pytest.mark.django_db
def test_personal_tokens(client, user):
    client.force_login(user)
    r = client.post("/accounts/tokens/", {"name": "CI", "scopes": "events:read"})
    assert r.status_code == 302
    raw = client.session["evac_new_token"]
    page = client.get("/accounts/tokens/").content.decode()
    assert raw in page and raw not in client.get("/accounts/tokens/").content.decode()  # shown once
    tok = ServiceToken.objects.get(owner=user)
    assert tok.token_hash == ServiceToken.hash_token(raw) and not tok.created_with_2fa
    client.post(f"/accounts/tokens/{tok.pk}/revoke/")
    assert not ServiceToken.objects.exists()


@pytest.mark.django_db
def test_gdpr_export(client, member, event):
    client.force_login(member)
    r = client.get("/accounts/privacy/export/")
    data = r.json()
    assert data["account"]["email"] == member.email and data["memberships"][0]["event"] == "demo"
    assert "attachment" in r["Content-Disposition"]


@pytest.mark.django_db
def test_gdpr_delete(client, member, event):
    Notification.objects.create(user=member, title="x")
    client.force_login(member)
    r = client.post("/accounts/privacy/delete/", {"confirm": "wrong@example.org", "password": "pw-alice-12345"})
    assert "does not match" in r.content.decode()
    r = client.post("/accounts/privacy/delete/", {"confirm": member.email, "password": "nope"})
    assert "Wrong password" in r.content.decode()
    r = client.post("/accounts/privacy/delete/", {"confirm": member.email, "password": "pw-alice-12345"})
    assert r.status_code == 302
    member.refresh_from_db()
    assert not member.is_active and member.email.startswith("deleted-") and not member.memberships.exists()
    assert not Notification.objects.filter(user=member).exists()


@pytest.mark.django_db
def test_last_admin_cannot_delete_account(client, admin, event):
    login_2fa(client, admin)
    r = client.post("/accounts/privacy/delete/", {"confirm": admin.email, "password": "pw-root-12345"})
    assert "last instance admin" in r.content.decode()
    other_admin = User.objects.create_superuser(email="root2@example.org", password="pw-root2-12345")
    assert other_admin
    r = client.post("/accounts/privacy/delete/", {"confirm": admin.email, "password": "pw-root-12345"})
    assert "only admin of Demo Camp" in r.content.decode()


@pytest.mark.django_db
def test_invitation_new_account(client, event, admin, role):
    inv, url = services.invite(event, "new@example.org", role("crew"), actor=admin)
    assert len(mail.outbox) == 1 and url in mail.outbox[0].body
    path = url.split("http://localhost:8000")[1]
    r = client.get(path)
    assert "Create account and join" in r.content.decode()
    pw = "a-long-password-1"
    r = client.post(path, {"display_name": "Newbie", "password1": pw, "password2": pw})
    assert r.status_code == 302
    user = User.objects.get(email="new@example.org")
    assert user.email_verified and event.memberships.filter(user=user).exists()
    inv.refresh_from_db()
    assert inv.accepted_by == user
    client.logout()
    assert client.get(path).status_code == 404  # used


@pytest.mark.django_db
def test_invitation_existing_account(client, event, admin, other, role):
    _inv, url = services.invite(event, other.email, role("crew"), actor=admin, send=False)
    path = url.split("http://localhost:8000")[1]
    assert "already have an account" in client.get(path).content.decode()
    client.force_login(other)
    r = client.post(path)
    assert r.status_code == 302 and event.memberships.filter(user=other).exists()


@pytest.mark.django_db
def test_invitation_password_mismatch(client, event, admin, role):
    _inv, url = services.invite(event, "x@example.org", role("crew"), actor=admin, send=False)
    path = url.split("http://localhost:8000")[1]
    r = client.post(path, {"password1": "a-long-password-1", "password2": "different-password-2"})
    assert "do not match" in r.content.decode()
    assert client.get("/invite/garbage/").status_code == 404


@pytest.mark.django_db
def test_logout(client, user):
    client.force_login(user)
    r = client.post("/accounts/logout/")
    assert r.status_code == 302
    assert client.get("/accounts/profile/").status_code == 302
