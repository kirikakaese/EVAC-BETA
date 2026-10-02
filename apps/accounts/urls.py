# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("2fa/verify/", views.twofactor_verify, name="twofactor_verify"),
    path("2fa/webauthn/options/", views.webauthn_login_options, name="webauthn_login_options"),
    path("2fa/webauthn/verify/", views.webauthn_login_verify, name="webauthn_login_verify"),
    path("oidc/login/", views.oidc_login, name="oidc_login"),
    path("oidc/callback/", views.oidc_callback, name="oidc_callback"),
    path("oidc/unlink/", views.oidc_unlink, name="oidc_unlink"),
    path("profile/", views.profile, name="profile"),
    path("security/", views.security, name="security"),
    path("security/totp/", views.totp_setup, name="totp_setup"),
    path("security/webauthn/options/", views.webauthn_register_options, name="webauthn_register_options"),
    path("security/webauthn/verify/", views.webauthn_register_verify, name="webauthn_register_verify"),
    path("security/<str:kind>/<int:pk>/delete/", views.factor_delete, name="factor_delete"),
    path("security/recovery-codes/", views.recovery_regenerate, name="recovery_regenerate"),
    path("tokens/", views.tokens, name="tokens"),
    path("tokens/<uuid:pk>/revoke/", views.token_revoke, name="token_revoke"),
    path("privacy/export/", views.gdpr_export, name="gdpr_export"),
    path("privacy/delete/", views.gdpr_delete, name="gdpr_delete"),
]
