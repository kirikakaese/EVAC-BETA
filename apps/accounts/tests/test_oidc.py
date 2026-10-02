# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenID Connect login: flow, callback validation, account linking, MFA trust, SSO-only mode."""
from __future__ import annotations

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from apps.accounts import oidc, twofactor
from apps.accounts.models import TOTPDevice, User
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db

ISSUER = "https://id.example.org/realms/evac"
CLIENT_ID = "evac-client"
DISCOVERY = {
    "issuer": ISSUER,
    "authorization_endpoint": ISSUER + "/protocol/openid-connect/auth",
    "token_endpoint": ISSUER + "/protocol/openid-connect/token",
    "userinfo_endpoint": ISSUER + "/protocol/openid-connect/userinfo",
    "end_session_endpoint": ISSUER + "/protocol/openid-connect/logout",
    "jwks_uri": ISSUER + "/protocol/openid-connect/certs",
    "code_challenge_methods_supported": ["S256"],
    "claims_supported": ["sub", "email", "email_verified", "preferred_username", "name"],
}
OIDC_ON = dict(EVAC_OIDC_ENABLED=True, EVAC_OIDC_ISSUER=ISSUER, EVAC_OIDC_CLIENT_ID=CLIENT_ID,
               EVAC_OIDC_CLIENT_SECRET="s3cret", EVAC_OIDC_SCOPES="openid email profile",
               EVAC_OIDC_AUTO_CREATE=True, EVAC_OIDC_TRUST_EMAIL_VERIFIED=True, EVAC_OIDC_ALLOW_PASSWORD_LOGIN=True,
               EVAC_OIDC_LOGOUT_AT_IDP=False,
               EVAC_OIDC_BUTTON_LABEL="Log in with SSO")


def oidc_settings(**overrides):
    return override_settings(**{**OIDC_ON, **overrides})


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_id_token(**overrides) -> str:
    now = int(time.time())
    payload = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "user-123", "exp": now + 300, "iat": now,
               "nonce": overrides.pop("nonce", "NONCE"), "email": "sso@example.org", "email_verified": True,
               "preferred_username": "ssouser", "name": "Sso User"}
    payload.update(overrides)
    header = b64url(json.dumps({"alg": "RS256", "kid": "x"}).encode())
    return f"{header}.{b64url(json.dumps(payload).encode())}.{b64url(b'dummy-signature')}"


class FakeResponse:
    def __init__(self, data, status=200, text=None, headers=None):
        self._data, self.status_code, self.headers = data, status, headers or {"Content-Type": "application/json"}
        self.text = text if text is not None else json.dumps(data)

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class FakeRequests:
    """Stand-in for the ``requests`` module: discovery, token endpoint and userinfo are scripted."""

    RequestException = requests.RequestException
    HTTPError = requests.HTTPError

    def __init__(self, discovery=DISCOVERY, userinfo=None, token_status=200):
        self.discovery = discovery
        self.userinfo = userinfo
        self.token_status = token_status
        self.calls = []
        self.id_token_overrides = {}
        self.fail_discovery = False

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        if url.endswith("/.well-known/openid-configuration"):
            if self.fail_discovery:
                raise requests.ConnectionError("down")
            return FakeResponse(self.discovery)
        if url == DISCOVERY["userinfo_endpoint"]:
            assert kw["headers"]["Authorization"] == "Bearer AT"
            return FakeResponse(self.userinfo if self.userinfo is not None else {"sub": "user-123"})
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, data=None, **kw):
        self.calls.append(("POST", url, {"data": data, **kw}))
        assert url == DISCOVERY["token_endpoint"]
        # nonce must be the one EVAC issued: the test passes it via ``id_token_overrides``
        nonce = self.id_token_overrides.pop("nonce", None) or self._nonce
        if self.token_status != 200:
            return FakeResponse({"error": "invalid_grant"}, status=self.token_status)
        return FakeResponse({"access_token": "AT", "token_type": "Bearer",
                             "id_token": make_id_token(nonce=nonce, **self.id_token_overrides)})


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def fake(monkeypatch):
    f = FakeRequests()
    monkeypatch.setattr(oidc, "requests", f)
    return f


def start(client, fake, next_url=None, link=False):
    params = {"next": next_url} if next_url else {}
    if link:
        r = client.post(reverse("accounts:oidc_login"), {"link": "1"})
    else:
        r = client.get(reverse("accounts:oidc_login"), params)
    assert r.status_code == 302, r.status_code
    q = {k: v[0] for k, v in parse_qs(urlparse(r.url).query).items()}
    fake._nonce = q["nonce"]
    return r.url, q


def callback(client, q, **extra):
    return client.get(reverse("accounts:oidc_callback"), {"state": q["state"], "code": "CODE", **extra})


@pytest.fixture
def anyuser(db):
    return User.objects.create_user(email="first@example.org", password="pw-first-12345")


def test_disabled_by_default(client, anyuser):
    assert client.get(reverse("accounts:oidc_login")).status_code == 404
    assert client.get(reverse("accounts:oidc_callback")).status_code == 404


def test_start_flow_uses_pkce(client, fake, anyuser):
    with oidc_settings():
        url, q = start(client, fake, next_url="/e/demo/")
    assert url.startswith(DISCOVERY["authorization_endpoint"])
    flow = client.session[oidc.SESSION_FLOW_KEY]
    challenge = b64url(hashlib.sha256(flow["verifier"].encode()).digest())
    assert q["code_challenge"] == challenge and q["code_challenge_method"] == "S256"
    assert q["client_id"] == CLIENT_ID and flow["next"] == "/e/demo/"


def test_callback_creates_account(client, fake, anyuser):
    with oidc_settings():
        _url, q = start(client, fake)
        r = callback(client, q)
    assert r.status_code == 302
    user = User.objects.get(email="sso@example.org")
    assert user.oidc_subject == f"{ISSUER}|user-123" and user.email_verified and not user.has_usable_password()
    assert user.display_name == "Sso User"
    assert AuditLog.objects.filter(action="account.created").exists()
    assert not twofactor.is_verified(client)


def test_callback_links_verified_existing_account(client, fake, anyuser):
    existing = User.objects.create_user(email="sso@example.org", password="pw-sso-123456", email_verified=False)
    with oidc_settings():
        _url, q = start(client, fake)
        callback(client, q)
    existing.refresh_from_db()
    assert existing.oidc_subject.endswith("|user-123") and existing.email_verified


def test_unverified_idp_email_does_not_link(client, fake, anyuser):
    User.objects.create_user(email="sso@example.org", password="pw-sso-123456")
    fake.id_token_overrides = {"email_verified": False}
    with oidc_settings():
        _url, q = start(client, fake)
        r = callback(client, q)
    assert r.status_code == 403


def test_state_mismatch_and_errors(client, fake, anyuser):
    with oidc_settings():
        _url, q = start(client, fake)
        assert client.get(reverse("accounts:oidc_callback"), {"state": "forged", "code": "C"}).status_code == 400
        _url, q = start(client, fake)
        assert callback(client, q, error="access_denied").status_code == 400
        _url, q = start(client, fake)
        assert client.get(reverse("accounts:oidc_callback"), {"state": q["state"]}).status_code == 400


def test_bad_tokens_are_rejected(client, fake, anyuser):
    for overrides in ({"aud": "someone-else"}, {"iss": "https://evil"}, {"exp": int(time.time()) - 3600},
                      {"nonce": "wrong"}):
        with oidc_settings():
            _url, q = start(client, fake)
            fake.id_token_overrides = dict(overrides)
            r = callback(client, q)
        assert r.status_code == 400, overrides
    fake.token_status = 400
    with oidc_settings():
        _url, q = start(client, fake)
        assert callback(client, q).status_code == 400


def test_discovery_failure(client, fake, anyuser):
    fake.fail_discovery = True
    with oidc_settings():
        assert client.get(reverse("accounts:oidc_login")).status_code == 503


def test_user_with_local_2fa_must_complete_it(client, fake, anyuser):
    user = User.objects.create_user(email="sso@example.org", password="pw-sso-123456", email_verified=True)
    dev = TOTPDevice(user=user, confirmed=True)
    dev.secret = "JBSWY3DPEHPK3PXP"
    dev.save()
    with oidc_settings():
        _url, q = start(client, fake)
        r = callback(client, q)
    assert r["Location"] == reverse("accounts:twofactor_verify")


def test_idp_mfa_is_trusted_when_configured(client, fake, anyuser):
    fake.id_token_overrides = {"amr": ["pwd", "otp"]}
    with oidc_settings(EVAC_OIDC_TRUST_MFA=True):
        _url, q = start(client, fake)
        callback(client, q)
    assert twofactor.is_verified(client)


def test_auto_create_off(client, fake, anyuser):
    with oidc_settings(EVAC_OIDC_AUTO_CREATE=False):
        _url, q = start(client, fake)
        assert callback(client, q).status_code == 403


def test_link_and_unlink(client, fake, anyuser):
    client.force_login(anyuser)
    with oidc_settings():
        _url, q = start(client, fake, link=True)
        r = callback(client, q)
        assert r["Location"] == reverse("accounts:security")
        anyuser.refresh_from_db()
        assert anyuser.oidc_subject.endswith("|user-123")
        client.post(reverse("accounts:oidc_unlink"))
    anyuser.refresh_from_db()
    assert anyuser.oidc_subject == ""


def test_sso_only_mode_hides_password_login(client, anyuser):
    with oidc_settings(EVAC_OIDC_ALLOW_PASSWORD_LOGIN=False):
        page = client.get(reverse("accounts:login")).content.decode()
        assert "Log in with SSO" in page and 'name="password"' not in page
        assert client.post(reverse("accounts:login"), {"email": "a@b.c", "password": "x"}).status_code == 404
