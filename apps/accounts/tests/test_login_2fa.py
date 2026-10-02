# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from unittest import mock

import pyotp
import pytest
from django.test import override_settings

from apps.accounts import twofactor
from apps.accounts.models import RecoveryCode, TOTPDevice, WebAuthnCredential
from apps.core.models import AuditLog
from conftest import login_2fa, totp_now


@pytest.mark.django_db
def test_password_login(client, user):
    r = client.post("/accounts/login/", {"email": "ALICE@example.org", "password": "pw-alice-12345"})
    assert r.status_code == 302
    assert client.get("/accounts/profile/").status_code == 200
    assert AuditLog.objects.filter(action="account.login").exists()
    assert client.get("/accounts/login/").status_code == 302  # already logged in


@pytest.mark.django_db
@override_settings(EVAC_LOGIN_MAX_FAILURES=2)
def test_lockout(client, user):
    for _ in range(2):
        r = client.post("/accounts/login/", {"email": user.email, "password": "wrong-password"})
        assert "wrong" in r.content.decode()
    r = client.post("/accounts/login/", {"email": user.email, "password": "pw-alice-12345"})
    assert "Too many failed attempts" in r.content.decode()


def _enrol_totp(client, user):
    client.force_login(user)
    client.get("/accounts/security/totp/")
    dev = TOTPDevice.objects.get(user=user, confirmed=False)
    r = client.post("/accounts/security/totp/", {"name": "Phone", "code": "000000"})
    assert "not valid" in r.content.decode()
    r = client.post("/accounts/security/totp/", {"name": "Phone", "code": totp_now(dev)})
    assert r.status_code == 302
    dev.refresh_from_db()
    assert dev.confirmed and dev.secret_encrypted != dev.secret
    return dev


@pytest.mark.django_db
def test_totp_enrolment_and_login(client, user):
    dev = _enrol_totp(client, user)
    assert twofactor.is_verified(client)  # session verified after enrolment
    codes = client.session.get("evac_new_recovery_codes")
    assert len(codes) == 10
    assert "Your recovery codes" in client.get("/accounts/security/").content.decode()
    client.logout()
    r = client.post("/accounts/login/", {"email": user.email, "password": "pw-alice-12345"})
    assert r["Location"] == "/accounts/2fa/verify/"
    assert client.get("/accounts/profile/").status_code == 302  # not logged in yet
    assert "not valid" in client.post("/accounts/2fa/verify/", {"code": "123456"}).content.decode()
    # replay protection: the code used at enrolment step cannot be reused within its window
    totp = pyotp.TOTP(dev.secret)
    TOTPDevice.objects.filter(pk=dev.pk).update(last_counter=-1)
    r = client.post("/accounts/2fa/verify/", {"code": totp.now()})
    assert r.status_code == 302
    assert client.session[twofactor.SESSION_KEY]
    dev.refresh_from_db()
    assert not twofactor.verify_totp(user, totp.at(int(dev.last_counter) * 30))  # replay rejected


@pytest.mark.django_db
def test_recovery_code_login(client, user):
    _enrol_totp(client, user)
    codes = client.session["evac_new_recovery_codes"]
    client.logout()
    client.post("/accounts/login/", {"email": user.email, "password": "pw-alice-12345"})
    r = client.post("/accounts/2fa/verify/", {"recovery": codes[0].upper()})
    assert r.status_code == 302 and twofactor.remaining_recovery_codes(user) == 9
    client.logout()
    client.post("/accounts/login/", {"email": user.email, "password": "pw-alice-12345"})
    assert "not valid" in client.post("/accounts/2fa/verify/", {"recovery": codes[0]}).content.decode()


@pytest.mark.django_db
def test_verify_without_pending_redirects(client, user):
    assert client.get("/accounts/2fa/verify/")["Location"] == "/accounts/login/"


@pytest.mark.django_db
def test_factor_management_requires_verified_session(client, user):
    dev = _enrol_totp(client, user)
    client.logout()
    client.force_login(user)  # password-only session
    r = client.post(f"/accounts/security/totp/{dev.pk}/delete/")
    assert TOTPDevice.objects.filter(pk=dev.pk).exists()
    client.post("/accounts/security/recovery-codes/")
    assert RecoveryCode.objects.filter(user=user, used_at__isnull=True).count() == 10
    login_2fa(client, user)
    client.post("/accounts/security/recovery-codes/")
    assert client.session.get("evac_new_recovery_codes")
    r = client.post(f"/accounts/security/totp/{dev.pk}/delete/")
    assert r.status_code == 302 and not TOTPDevice.objects.filter(pk=dev.pk).exists()
    assert client.post("/accounts/security/nope/1/delete/").status_code == 404


@pytest.mark.django_db
def test_webauthn_registration_and_login(client, user):
    client.force_login(user)
    opts = json.loads(client.post("/accounts/security/webauthn/options/").content)
    assert opts["rp"]["id"] == "testserver" and opts["user"]["name"] == user.email
    fake = mock.Mock(credential_id=b"cred-1", credential_public_key=b"pk", sign_count=0)
    with mock.patch("webauthn.verify_registration_response", return_value=fake):
        r = client.post("/accounts/security/webauthn/verify/", json.dumps({"credential": {"id": "x"}, "name": "Key"}),
                        content_type="application/json")
    assert r.status_code == 200
    cred = WebAuthnCredential.objects.get(user=user)
    assert cred.name == "Key"
    # failure path
    r = client.post("/accounts/security/webauthn/verify/", "{}", content_type="application/json")
    assert r.status_code == 400
    client.logout()
    client.post("/accounts/login/", {"email": user.email, "password": "pw-alice-12345"})
    opts = json.loads(client.post("/accounts/2fa/webauthn/options/").content)
    assert opts["allowCredentials"][0]["id"] == cred.credential_id
    with mock.patch("webauthn.verify_authentication_response", return_value=mock.Mock(new_sign_count=5)):
        r = client.post("/accounts/2fa/webauthn/verify/", json.dumps({"id": cred.credential_id}),
                        content_type="application/json")
    assert r.status_code == 200 and "redirect" in r.json()
    cred.refresh_from_db()
    assert cred.sign_count == 5 and client.session[twofactor.SESSION_KEY]


@pytest.mark.django_db
def test_webauthn_login_rejects_bad_assertion(client, user):
    WebAuthnCredential.objects.create(user=user, credential_id="abc", public_key="cGs")
    client.post("/accounts/login/", {"email": user.email, "password": "pw-alice-12345"})
    client.post("/accounts/2fa/webauthn/options/")
    with mock.patch("webauthn.verify_authentication_response", side_effect=ValueError("bad")):
        r = client.post("/accounts/2fa/webauthn/verify/", json.dumps({"id": "abc"}), content_type="application/json")
    assert r.status_code == 400
    assert client.post("/accounts/2fa/webauthn/verify/", "nope", content_type="application/json").status_code == 400


@pytest.mark.django_db
def test_webauthn_endpoints_without_pending(client, user):
    assert client.post("/accounts/2fa/webauthn/options/").status_code == 400
    assert client.post("/accounts/2fa/webauthn/verify/", "{}", content_type="application/json").status_code == 400


@pytest.mark.django_db
def test_admin_can_reset_2fa(client, admin, user):
    _enrol_totp(client, user)
    login_2fa(client, admin)
    client.post(f"/settings/users/{user.pk}/", {"action": "reset_2fa"})
    assert not user.has_two_factor
