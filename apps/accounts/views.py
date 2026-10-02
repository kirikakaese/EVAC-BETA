# SPDX-License-Identifier: AGPL-3.0-or-later
"""Login (password + second factor, or OIDC), profile, security (2FA), tokens, GDPR export/delete,
invitation acceptance."""
from __future__ import annotations

import json
import logging
import secrets

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.audit import client_ip, log
from apps.events import services as event_services

from . import gdpr, oidc, twofactor
from .models import ServiceToken, TOTPDevice, User

seclog = logging.getLogger("evac.security")
FAIL_WINDOW = 15 * 60


# --------------------------------------------------------------------------- lockout helpers

def _keys(request, email: str) -> tuple[str, str]:
    return f"lf:ip:{client_ip(request)}", f"lf:acct:{(email or '').strip().lower()}"


def _locked(request, email: str) -> bool:
    limit = int(getattr(settings, "EVAC_LOGIN_MAX_FAILURES", 5))
    ip_key, acct_key = _keys(request, email)
    return (cache.get(acct_key, 0) >= limit) or (cache.get(ip_key, 0) >= limit * 6)


def _fail(request, email: str) -> None:
    lock = int(getattr(settings, "EVAC_LOGIN_LOCKOUT_MINUTES", 15)) * 60
    for key in _keys(request, email):
        cache.add(key, 0, max(lock, FAIL_WINDOW))
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, max(lock, FAIL_WINDOW))
    seclog.info("login failure email=%s ip=%s", email, client_ip(request))


def _clear(request, email: str) -> None:
    cache.delete(_keys(request, email)[1])


def _safe_next(request, url: str | None) -> str:
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return url
    return ""


def complete_login(request, user: User, *, method: str, next_url: str = "", mfa_done: bool = False):
    """Finish a first-factor login: go through the second factor when the user has one."""
    if user.has_two_factor and not mfa_done:
        request.session[twofactor.PENDING_KEY] = str(user.pk)
        request.session[twofactor.PENDING_NEXT_KEY] = next_url
        request.session["evac_2fa_method"] = method
        return redirect("accounts:twofactor_verify")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    if mfa_done:
        twofactor.mark_verified(request)
    log(action="account.login", actor=user, target=user, request=request, message=f"Login ({method})")
    return redirect(next_url or settings.LOGIN_REDIRECT_URL)


# --------------------------------------------------------------------------- login / logout

class LoginForm(forms.Form):
    email = forms.EmailField(label=gettext_lazy("E-mail address"),
                             widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}))
    password = forms.CharField(label=gettext_lazy("Password"),
                               widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


@require_http_methods(["GET", "POST"])
def login_view(request):
    next_url = _safe_next(request, request.POST.get("next") or request.GET.get("next"))
    if request.user.is_authenticated:
        return redirect(next_url or settings.LOGIN_REDIRECT_URL)
    form = LoginForm(request.POST or None)
    if request.method == "POST":
        if not oidc.password_login_allowed():
            raise Http404
        email = request.POST.get("email", "")
        if _locked(request, email):
            form.add_error(None, _("Too many failed attempts. Please wait a few minutes and try again."))
        elif form.is_valid():
            user = authenticate(request, email=form.cleaned_data["email"].lower(),
                                password=form.cleaned_data["password"])
            if user is None:
                _fail(request, email)
                form.add_error(None, _("E-mail address or password is wrong."))
            else:
                _clear(request, email)
                return complete_login(request, user, method="password", next_url=next_url)
    return render(request, "accounts/login.html", {"form": form, "next": next_url, **oidc.template_context()})


class TOTPForm(forms.Form):
    code = forms.CharField(label=gettext_lazy("Code"), max_length=20, required=False,
                           widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric",
                                                         "autofocus": True}))
    recovery = forms.CharField(label=gettext_lazy("Or a recovery code"), max_length=20, required=False)


@require_http_methods(["GET", "POST"])
def twofactor_verify(request):
    uid = request.session.get(twofactor.PENDING_KEY)
    user = User.objects.filter(pk=uid, is_active=True).first() if uid else None
    if user is None:
        return redirect("accounts:login")
    form = TOTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _locked(request, user.email):
            form.add_error(None, _("Too many failed attempts. Please wait a few minutes and try again."))
        else:
            ok = (form.cleaned_data["code"] and twofactor.verify_totp(user, form.cleaned_data["code"])) or (
                form.cleaned_data["recovery"] and twofactor.use_recovery_code(user, form.cleaned_data["recovery"]))
            if ok:
                return _finish_2fa(request, user)
            _fail(request, user.email)
            form.add_error(None, _("That code is not valid."))
    return render(request, "accounts/twofactor_verify.html", {
        "form": form, "has_totp": user.totp_devices.filter(confirmed=True).exists(),
        "has_webauthn": user.webauthn_credentials.exists()})


def _finish_2fa(request, user):
    method = request.session.pop("evac_2fa_method", "password")
    next_url = request.session.pop(twofactor.PENDING_NEXT_KEY, "")
    request.session.pop(twofactor.PENDING_KEY, None)
    _clear(request, user.email)
    return complete_login(request, user, method=f"{method}+2fa", next_url=next_url, mfa_done=True)


@require_POST
def webauthn_login_options(request):
    uid = request.session.get(twofactor.PENDING_KEY)
    user = User.objects.filter(pk=uid, is_active=True).first() if uid else None
    if user is None or not user.webauthn_credentials.exists():
        return JsonResponse({"error": "no pending login"}, status=400)
    return HttpResponse(twofactor.webauthn_auth_options(request, user), content_type="application/json")


@require_POST
def webauthn_login_verify(request):
    uid = request.session.get(twofactor.PENDING_KEY)
    user = User.objects.filter(pk=uid, is_active=True).first() if uid else None
    if user is None:
        return JsonResponse({"error": "no pending login"}, status=400)
    try:
        credential = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "invalid"}, status=400)
    if _locked(request, user.email) or not twofactor.webauthn_auth_verify(request, user, credential):
        _fail(request, user.email)
        return JsonResponse({"error": _("The security key could not be verified.")}, status=400)
    resp = _finish_2fa(request, user)
    return JsonResponse({"redirect": resp.url})


class LogoutView(auth_views.LogoutView):
    def post(self, request, *args, **kwargs):
        id_token = request.session.get(oidc.SESSION_ID_TOKEN_KEY)
        if request.user.is_authenticated:
            log(action="account.logout", actor=request.user, target=request.user, request=request)
        response = super().post(request, *args, **kwargs)
        if id_token:
            url = oidc.end_session_url(id_token, request.build_absolute_uri(getattr(response, "url", None) or "/"))
            if url:
                return redirect(url)
        return response


# --------------------------------------------------------------------------- OIDC

def _oidc_error(request, message, status=400):
    return render(request, "accounts/oidc_error.html", {"message": message}, status=status)


@require_http_methods(["GET", "POST"])
def oidc_login(request):
    if not oidc.enabled():
        raise Http404
    data = request.POST if request.method == "POST" else request.GET
    link = bool(data.get("link")) and request.user.is_authenticated
    if request.user.is_authenticated and not link:
        return redirect(settings.LOGIN_REDIRECT_URL)
    try:
        return redirect(oidc.start_flow(request, next_url=data.get("next", ""), link=link))
    except oidc.OIDCError as exc:
        return _oidc_error(request, str(exc), status=503)


@require_http_methods(["GET"])
def oidc_callback(request):
    if not oidc.enabled():
        raise Http404
    if _locked(request, ""):
        return _oidc_error(request, _("Too many failed login attempts. Please wait a few minutes."), status=429)
    flow = oidc.pop_flow(request)
    state = request.GET.get("state", "")
    if not flow or not state or not secrets.compare_digest(state, flow["state"]):
        return _oidc_error(request, _("The login session is invalid or has expired. Please start again."))
    if request.GET.get("error"):
        desc = request.GET.get("error_description") or request.GET["error"]
        return _oidc_error(request, _("The single sign-on provider refused the login: %(e)s") % {"e": desc})
    code = request.GET.get("code", "")
    if not code:
        return _oidc_error(request, _("The login session is invalid or has expired. Please start again."))
    try:
        tokens = oidc.exchange_code(request, code, flow["verifier"])
        claims = oidc.claims_from_tokens(tokens, flow["nonce"])
    except oidc.OIDCError as exc:
        _fail(request, "")
        return _oidc_error(request, str(exc))
    if flow.get("link") and request.user.is_authenticated:
        try:
            oidc.link_user(request.user, claims, request=request)
        except oidc.OIDCError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Your single sign-on identity is now linked to this account."))
        return redirect("accounts:security")
    try:
        user, _how = oidc.resolve_user(claims, request=request)
    except oidc.OIDCError as exc:
        _fail(request, "")
        return _oidc_error(request, str(exc), status=403)
    if getattr(settings, "EVAC_OIDC_LOGOUT_AT_IDP", False) and tokens.get("id_token"):
        request.session[oidc.SESSION_ID_TOKEN_KEY] = tokens["id_token"]
    return complete_login(request, user, method="oidc", next_url=flow.get("next") or "", mfa_done=oidc.idp_mfa(claims))


# --------------------------------------------------------------------------- profile & security

class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["display_name"]


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    pw_form = PasswordChangeForm(request.user, request.POST or None, prefix="pw")
    if request.method == "POST":
        if "save_profile" in request.POST and form.is_valid():
            form.save()
            log(action="account.updated", actor=request.user, target=request.user, request=request)
            messages.success(request, _("Profile saved."))
            return redirect("accounts:profile")
        if "change_password" in request.POST and pw_form.is_valid():
            pw_form.save()
            update_session_auth_hash(request, pw_form.user)
            log(action="account.password_changed", actor=request.user, target=request.user, request=request)
            messages.success(request, _("Password changed."))
            return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form, "pw_form": pw_form})


@login_required
def security(request):
    user = request.user
    return render(request, "accounts/security.html", {
        "totp_devices": user.totp_devices.filter(confirmed=True),
        "webauthn": user.webauthn_credentials.all(),
        "recovery_left": twofactor.remaining_recovery_codes(user),
        "verified": twofactor.is_verified(request),
        "new_codes": request.session.pop("evac_new_recovery_codes", None),
        **oidc.template_context(),
    })


class TOTPSetupForm(forms.Form):
    name = forms.CharField(label=gettext_lazy("Name"), max_length=60, initial="Authenticator app")
    code = forms.CharField(label=gettext_lazy("Code from the app"), max_length=10,
                           widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}))


def _first_factor_added(request, user):
    """After enrolling the first factor the current session counts as verified; issue recovery codes."""
    twofactor.mark_verified(request)
    if twofactor.remaining_recovery_codes(user) == 0:
        request.session["evac_new_recovery_codes"] = twofactor.generate_recovery_codes(user)


@login_required
def totp_setup(request):
    user = request.user
    dev_id = request.session.get("evac_totp_setup")
    dev = TOTPDevice.objects.filter(pk=dev_id, user=user, confirmed=False).first() if dev_id else None
    if dev is None:
        dev = twofactor.new_totp(user)
        request.session["evac_totp_setup"] = dev.pk
    form = TOTPSetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dev.name = form.cleaned_data["name"]
        dev.save(update_fields=["name"])
        if twofactor.confirm_totp(dev, form.cleaned_data["code"]):
            request.session.pop("evac_totp_setup", None)
            _first_factor_added(request, user)
            messages.success(request, _("Authenticator app added."))
            return redirect("accounts:security")
        form.add_error("code", _("That code is not valid. Check the time on your phone and try again."))
    uri = twofactor.provisioning_uri(dev)
    return render(request, "accounts/totp_setup.html", {"form": form, "qr": twofactor.qr_svg(uri),
                                                        "secret": dev.secret})


@login_required
@require_POST
def webauthn_register_options(request):
    return HttpResponse(twofactor.webauthn_register_options(request, request.user), content_type="application/json")


@login_required
@require_POST
def webauthn_register_verify(request):
    try:
        data = json.loads(request.body or b"{}")
        twofactor.webauthn_register_verify(request, request.user, data.get("credential"), data.get("name", ""))
    except Exception as exc:  # noqa: BLE001 - shown to the user, details logged
        seclog.info("webauthn registration failed: %s", exc)
        return JsonResponse({"error": _("The security key could not be registered.")}, status=400)
    _first_factor_added(request, request.user)
    messages.success(request, _("Security key added."))
    return JsonResponse({"redirect": "/accounts/security/"})


@login_required
@require_POST
def factor_delete(request, kind, pk):
    if not twofactor.is_verified(request):
        messages.error(request, _("Log in with your second factor before removing one."))
        return redirect("accounts:security")
    model = {"totp": request.user.totp_devices, "webauthn": request.user.webauthn_credentials}.get(kind)
    if model is None:
        raise Http404
    obj = get_object_or_404(model, pk=pk)
    log(action="account.2fa_removed", actor=request.user, target=request.user, request=request,
        message=f"Second factor '{obj.name}' removed")
    obj.delete()
    messages.success(request, _("Second factor removed."))
    return redirect("accounts:security")


@login_required
@require_POST
def recovery_regenerate(request):
    if not twofactor.is_verified(request):
        messages.error(request, _("Log in with your second factor first."))
        return redirect("accounts:security")
    request.session["evac_new_recovery_codes"] = twofactor.generate_recovery_codes(request.user)
    return redirect("accounts:security")


@login_required
@require_POST
def oidc_unlink(request):
    user = request.user
    if not user.has_usable_password():
        messages.error(request, _("Set a password first - otherwise you could not log in anymore after unlinking."))
    elif user.oidc_subject:
        old, user.oidc_subject = user.oidc_subject, ""
        user.save(update_fields=["oidc_subject"])
        log(action="account.oidc_unlinked", actor=user, target=user, request=request,
            changes={"oidc_subject": [old, ""]})
        messages.success(request, _("The single sign-on identity was unlinked."))
    return redirect("accounts:security")


# --------------------------------------------------------------------------- personal tokens

class TokenForm(forms.Form):
    name = forms.CharField(label=gettext_lazy("Name"), max_length=120)
    scopes = forms.CharField(label=gettext_lazy("Scopes"), required=False, max_length=500,
                             help_text=gettext_lazy("Space separated, e.g. 'events:read venues:write'. "
                                                    "Empty = all of your rights."))
    expires_at = forms.DateTimeField(label=gettext_lazy("Expires"), required=False,
                                     widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))


def issue_token_from_form(request, form, event=None):
    tok, raw = ServiceToken.issue(name=form.cleaned_data["name"], owner=request.user, event=event,
                                  scopes=form.cleaned_data["scopes"].split(),
                                  expires_at=form.cleaned_data["expires_at"],
                                  created_with_2fa=twofactor.is_verified(request))
    log(action="token.created", actor=request.user, target=tok, event=event, request=request,
        message=f"Service token {tok.name} created", scope={"scopes": tok.scopes})
    request.session["evac_new_token"] = raw
    return tok


@login_required
def tokens(request):
    form = TokenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        issue_token_from_form(request, form)
        messages.warning(request, _("Copy the token now - it will not be shown again."))
        return redirect("accounts:tokens")
    return render(request, "accounts/tokens.html", {
        "form": form, "tokens": request.user.service_tokens.select_related("event"),
        "new_token": request.session.pop("evac_new_token", None)})


@login_required
@require_POST
def token_revoke(request, pk):
    tok = get_object_or_404(ServiceToken, pk=pk, owner=request.user)
    log(action="token.revoked", actor=request.user, target=tok, event=tok.event, request=request)
    tok.delete()
    messages.success(request, _("Token revoked."))
    return redirect(request.POST.get("next") if _safe_next(request, request.POST.get("next")) else "accounts:tokens")


# --------------------------------------------------------------------------- GDPR

@login_required
def gdpr_export(request):
    log(action="account.gdpr_export", actor=request.user, target=request.user, request=request)
    resp = JsonResponse(gdpr.export_user(request.user), json_dumps_params={"indent": 2})
    resp["Content-Disposition"] = f'attachment; filename="evac-account-{timezone.now():%Y%m%d}.json"'
    return resp


class DeleteForm(forms.Form):
    confirm = forms.CharField(label=gettext_lazy("Type your e-mail address to confirm"))
    password = forms.CharField(label=gettext_lazy("Password"), required=False, widget=forms.PasswordInput)


@login_required
def gdpr_delete(request):
    form = DeleteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        if form.cleaned_data["confirm"].strip().lower() != user.email.lower():
            form.add_error("confirm", _("This does not match your e-mail address."))
        elif user.has_usable_password() and not user.check_password(form.cleaned_data["password"]):
            form.add_error("password", _("Wrong password."))
        else:
            try:
                gdpr.delete_user(user, request=request)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
            else:
                logout(request)
                messages.success(request, _("Your account was deleted."))
                return redirect("accounts:login")
    return render(request, "accounts/gdpr_delete.html", {"form": form})


# --------------------------------------------------------------------------- invitations

class AcceptForm(forms.Form):
    display_name = forms.CharField(label=gettext_lazy("Your name"), max_length=120, required=False)
    password1 = forms.CharField(label=gettext_lazy("Choose a password"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=gettext_lazy("Repeat the password"), widget=forms.PasswordInput)

    def clean(self):
        from django.contrib.auth.password_validation import validate_password

        data = super().clean()
        if data.get("password1") != data.get("password2"):
            raise ValidationError(_("The passwords do not match."))
        if data.get("password1"):
            validate_password(data["password1"])
        return data


def invitation(request, token):
    inv = event_services.lookup_invitation(token)
    if inv is None:
        return render(request, "accounts/invitation_invalid.html", status=404)
    existing = User.objects.filter(email__iexact=inv.email).first()
    if request.user.is_authenticated:
        if request.method == "POST":
            event_services.accept_invitation(inv, request.user, request=request)
            messages.success(request, _("Welcome to %(event)s!") % {"event": inv.event.name})
            return redirect("portal:event_dashboard", inv.event.slug)
        return render(request, "accounts/invitation.html", {"inv": inv, "mode": "accept"})
    if existing is not None:
        return render(request, "accounts/invitation.html", {"inv": inv, "mode": "login",
                                                            "login_url": f"/accounts/login/?next=/invite/{token}/"})
    form = AcceptForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(email=inv.email, password=form.cleaned_data["password1"],
                                        display_name=form.cleaned_data["display_name"], email_verified=True)
        log(action="account.created", actor=user, target=user, request=request,
            message="Account created via invitation")
        event_services.accept_invitation(inv, user, request=request)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, _("Welcome to %(event)s!") % {"event": inv.event.name})
        return redirect("portal:event_dashboard", inv.event.slug)
    return render(request, "accounts/invitation.html", {"inv": inv, "mode": "signup", "form": form,
                                                        **oidc.template_context()})
