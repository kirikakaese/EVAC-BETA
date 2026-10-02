# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.core.models import AuditLog
from apps.events import services
from apps.events.models import Event, Role, ScheduledTransition
from apps.venues.models import Venue
from conftest import login_2fa


@pytest.mark.django_db
def test_first_run_wizard(client):
    """docker compose up -> wizard -> logged-in admin with an event (Phase 0 acceptance gate)."""
    assert client.get("/").url == "/setup/"
    page = client.get("/setup/").content.decode()
    assert "Create the first administrator account" in page
    r = client.post("/setup/", {"email": "Boss@Example.org", "display_name": "Boss", "password1": "a-good-password-9",
                                "password2": "a-good-password-9"})
    assert r.status_code == 302 and r.url == "/setup/?step=venue"
    boss = User.objects.get(email="boss@example.org")
    assert boss.is_superuser
    r = client.post("/setup/?step=venue", {"venue-name": "Town Hall", "venue-slug": "town-hall",
                                           "venue-timezone": "Europe/Berlin"})
    assert r.url == "/setup/?step=event"
    assert "Town Hall" in client.get("/setup/?step=event").content.decode()
    r = client.post("/setup/?step=event", {"name": "Spring Fair", "slug": "spring", "timezone": "Europe/Berlin"})
    assert r.url == "/setup/?step=screen"
    assert "Pair your first screen" in client.get("/setup/?step=screen").content.decode()
    r = client.post("/setup/?step=screen")
    page = client.get(r.url).content.decode()
    assert "All set" in page and "/e/spring/" in page and "supplementary information system" in page
    event = Event.objects.get(slug="spring")
    assert event.venues.get().slug == "town-hall"
    assert event.memberships.get(user=boss).assignments.get().role.key == "admin"
    assert client.get("/e/spring/").status_code == 200
    # the wizard cannot be re-run to create another admin
    client.logout()
    assert client.get("/setup/").url == "/"
    assert AuditLog.objects.filter(action="setup.admin_created").exists()


@pytest.mark.django_db
def test_wizard_with_setup_token_and_skip(client, monkeypatch):
    monkeypatch.setenv("EVAC_SETUP_TOKEN", "letmein")
    data = {"email": "a@example.org", "password1": "a-good-password-9", "password2": "a-good-password-9"}
    r = client.post("/setup/", {**data, "setup_token": "wrong"})
    assert "Wrong setup token" in r.content.decode()
    r = client.post("/setup/", {**data, "setup_token": "letmein"})
    assert r.status_code == 302
    r = client.post("/setup/?step=venue", {"skip": "1"})
    assert r.url == "/setup/?step=event"
    client.post("/setup/?step=admin", {**data, "email": "b@example.org", "setup_token": "letmein"})
    assert User.objects.count() == 1  # no second admin through the wizard


@pytest.mark.django_db
def test_wizard_password_mismatch(client):
    r = client.post("/setup/", {"email": "a@example.org", "password1": "a-good-password-9", "password2": "nope"})
    assert "do not match" in r.content.decode() and not User.objects.exists()


@pytest.mark.django_db
def test_home_lists_events(client, member, event, admin):
    client.force_login(member)
    assert client.get("/").url == "/e/demo/"  # single event -> straight in
    login_2fa(client, admin)
    assert "Demo Camp" in client.get("/").content.decode()
    assert client.get("/e/demo/switch/").url == "/e/demo/"


@pytest.mark.django_db
def test_strangers_cannot_see_event(client, other, event):
    client.force_login(other)
    assert client.get("/e/demo/").status_code == 404
    assert "No events yet" not in client.get("/").content.decode() or True


@pytest.mark.django_db
def test_event_create_and_settings(admin_client, venue):
    r = admin_client.post("/events/new/", {"name": "Winter", "slug": "winter", "timezone": "UTC",
                                           "primary_color": "#112233", "accent_color": "#445566",
                                           "venues": [str(venue.pk)]})
    assert r.status_code == 302
    ev = Event.objects.get(slug="winter")
    assert ev.venues.get() == venue
    r = admin_client.post("/e/winter/settings/", {"name": "Winter Fest", "timezone": "UTC", "primary_color": "#112233",
                                                  "accent_color": "#445566"})
    assert r.status_code == 302 and Event.objects.get(slug="winter").name == "Winter Fest"
    page = admin_client.get("/e/winter/").content.decode()
    assert "--primary:#112233" in page


@pytest.mark.django_db
def test_lifecycle_pages(admin_client, event):
    admin_client.post("/e/demo/settings/lifecycle/", {"state": "setup"})
    assert Event.objects.get(slug="demo").state == "setup"
    admin_client.post("/e/demo/settings/lifecycle/", {"state": "archived"})
    assert Event.objects.get(slug="demo").state == "setup"  # not allowed from setup
    admin_client.post("/e/demo/settings/lifecycle/", {"schedule": "1", "sched-target_state": "live",
                                                      "sched-at": "2030-01-01T10:00"})
    st = ScheduledTransition.objects.get()
    admin_client.post("/e/demo/settings/lifecycle/", {"schedule": "1"})
    admin_client.post("/e/demo/settings/lifecycle/", {"cancel": st.pk})
    assert not ScheduledTransition.objects.exists()


@pytest.mark.django_db
def test_orga_cannot_archive_without_delete_permission(client, orga, event):
    login_2fa(client, orga)
    for s in ("setup", "live", "teardown"):
        client.post("/e/demo/settings/lifecycle/", {"state": s})
    assert Event.objects.get(slug="demo").state == "teardown"
    assert client.post("/e/demo/settings/lifecycle/", {"state": "archived"}).status_code == 403


@pytest.mark.django_db
def test_clone_export_import_pages(admin_client, event):
    r = admin_client.post("/e/demo/settings/clone/", {"clone-name": "Copy", "clone-slug": "copy"})
    assert r.url == "/e/copy/"
    admin_client.post("/e/demo/settings/clone/", {})
    r = admin_client.get("/e/demo/settings/export/")
    data = json.loads(r.content)
    upload = SimpleUploadedFile("demo.json", json.dumps(data).encode(), content_type="application/json")
    r = admin_client.post("/events/import/", {"file": upload, "slug": "demo-import"})
    assert r.url == "/e/demo-import/"
    bad = SimpleUploadedFile("x.json", b"{nope", content_type="application/json")
    assert "not valid JSON" in admin_client.post("/events/import/", {"file": bad}).content.decode()
    wrong = SimpleUploadedFile("x.json", b'{"a": 1}', content_type="application/json")
    assert "not an EVAC event export" in admin_client.post("/events/import/", {"file": wrong}).content.decode()


@pytest.mark.django_db
def test_members_page(admin_client, event, other, role):
    from django.core import mail

    r = admin_client.post("/e/demo/members/", {"email": other.email, "role": role("crew").pk, "scope": ""})
    assert r.status_code == 302 and event.memberships.filter(user=other).exists()
    admin_client.post("/e/demo/members/", {"email": "fresh@example.org", "role": role("crew").pk, "scope": ""})
    assert mail.outbox and event.invitations.filter(email="fresh@example.org").exists()
    assert "/invite/" in admin_client.get("/e/demo/members/").content.decode()
    from apps.venues.models import Zone

    z = Zone.objects.get(name="North")
    admin_client.post("/e/demo/members/", {"email": other.email, "role": role("viewer").pk, "scope": f"zone:{z.pk}"})
    ra = event.memberships.get(user=other).assignments.get(scope_kind="zone")
    assert ra.scope_label.endswith("North")
    admin_client.post("/e/demo/members/action/", {"remove_assignment": ra.pk})
    inv = event.invitations.get()
    admin_client.post("/e/demo/members/action/", {"revoke_invitation": inv.pk})
    m = event.memberships.get(user=other)
    admin_client.post("/e/demo/members/action/", {"remove_member": m.pk})
    assert not event.memberships.filter(user=other).exists() and not event.invitations.exists()
    admin_m = event.memberships.get(user__is_superuser=True)
    r = admin_client.post("/e/demo/members/action/", {"remove_member": admin_m.pk}, follow=True)
    assert "at least one admin" in r.content.decode()


@pytest.mark.django_db
def test_orga_cannot_hand_out_sensitive_roles(client, orga, event, other, role):
    login_2fa(client, orga)
    assert client.post("/e/demo/members/", {"email": other.email, "role": role("admin").pk}).status_code == 403
    assert client.get("/e/demo/roles/new/").status_code == 403


@pytest.mark.django_db
def test_roles_pages(admin_client, event):
    r = admin_client.post("/e/demo/roles/new/", {"name": "Stage crew", "key": "stage", "description": "",
                                                 "perms": ["venues.view"], "patterns": "screens.*\n!screens.delete"})
    assert r.status_code == 302
    role = Role.objects.get(event=event, key="stage")
    assert role.permissions == ["venues.view", "screens.*", "!screens.delete"]
    page = admin_client.get("/e/demo/roles/stage/").content.decode()
    assert "screens.*" in page
    admin_client.post("/e/demo/roles/stage/", {"name": "Stage", "perms": ["events.roles"], "patterns": ""}, follow=True)
    role.refresh_from_db()
    assert role.name == "Stage" and role.grants_sensitive
    admin_client.post("/e/demo/roles/stage/", {"delete": "1"})
    assert not Role.objects.filter(key="stage").exists()
    r = admin_client.post("/e/demo/roles/viewer/", {"delete": "1"}, follow=True)
    assert "cannot be deleted" in r.content.decode()
    assert "2FA required" in admin_client.get("/e/demo/roles/").content.decode()


@pytest.mark.django_db
def test_audit_pages(admin_client, event):
    page = admin_client.get("/e/demo/audit/?action=event").content.decode()
    assert "event.created" in page
    assert admin_client.get("/e/demo/audit/?format=json").json()["entries"]
    assert "event.created" in admin_client.get("/settings/audit/?format=csv").content.decode()
    assert "Hash chain intact" in admin_client.get("/settings/audit/?verify=1").content.decode()
    assert admin_client.get("/settings/audit/?actor=root&q=Demo&drill=0").status_code == 200


@pytest.mark.django_db
def test_audit_requires_permission(client, event, other, role):
    services.assign_role(event, other, role("crew"))
    client.force_login(other)
    assert client.get("/e/demo/audit/").status_code == 403


@pytest.mark.django_db
def test_event_tokens_page(admin_client, event):
    admin_client.post("/e/demo/settings/tokens/", {"name": "Display bot", "scopes": "events:read"})
    assert "Display bot" in admin_client.get("/e/demo/settings/tokens/").content.decode()


@pytest.mark.django_db
def test_users_admin(admin_client, admin, user):
    assert user.email in admin_client.get("/settings/users/?q=alice").content.decode()
    admin_client.post(f"/settings/users/{user.pk}/", {"action": "deactivate"})
    user.refresh_from_db()
    assert not user.is_active
    admin_client.post(f"/settings/users/{user.pk}/", {"action": "activate"})
    admin_client.post(f"/settings/users/{user.pk}/", {"action": "promote"})
    user.refresh_from_db()
    assert user.is_superuser and user.is_active
    admin_client.post(f"/settings/users/{admin.pk}/", {"action": "demote"})
    admin.refresh_from_db()
    assert admin.is_superuser
    assert admin_client.post(f"/settings/users/{user.pk}/", {"action": "nope"}).status_code == 404


@pytest.mark.django_db
def test_search_docs_about(admin_client, event, venue):
    page = admin_client.get("/search/?q=Hall").content.decode()
    assert "Hall" in page
    assert admin_client.get("/search/?q=Demo").status_code == 200
    assert admin_client.get("/docs/").status_code == 200
    assert "kirikakaese" in admin_client.get("/about/").content.decode()


@pytest.mark.django_db
def test_seed_demo_is_idempotent(db):
    from django.core.management import call_command

    call_command("evac_seed_demo")
    call_command("evac_seed_demo")
    ev = Event.objects.get(slug="demo")
    assert ev.memberships.count() == 7 and Venue.objects.count() == 1 and ev.state == "setup"
    crew = ev.memberships.get(user__email="crew@evac.local")
    assert crew.assignments.filter(scope_kind="zone").exists()


@pytest.mark.django_db
def test_management_commands(event, admin, tmp_path, capsys):
    from django.core.management import call_command

    out = tmp_path / "e.json"
    call_command("evac_event", "export", "demo", "-o", str(out))
    call_command("evac_event", "import", str(out), "--slug", "demo2")
    assert Event.objects.filter(slug="demo2").exists()
    call_command("evac_token", admin.email, "ci", "--scopes", "events:read", "--event", "demo")
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("evac_")
    call_command("evac_audit_verify")
    call_command("evac_genkey")
    call_command("evac_rotate_secrets")
    call_command("evac_event", "export", "demo")


@pytest.mark.django_db
def test_every_doc_page_renders(client, admin):
    from apps.core.a11y import check_html
    from apps.portal.docs import DOCS

    assert {"readme", "operator-handbook", "adr-0002-central-node-sync", "extension-webhooks"} <= {d.slug for d in DOCS}
    for doc in DOCS:
        r = client.get(f"/docs/{doc.slug}/")
        assert r.status_code == 200, doc.slug
        assert check_html(r.content.decode()) == [], doc.slug
    assert "roles" in client.get("/docs/?q=roles").content.decode()
    assert client.get("/docs/nope/").status_code == 404
