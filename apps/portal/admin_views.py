# SPDX-License-Identifier: AGPL-3.0-or-later
"""Portal: members, roles, invitations, modules, settings namespaces, audit log, tokens, users."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.views import TokenForm, issue_token_from_form
from apps.core import modules, settings_store
from apps.core.audit import export_csv, export_rows, log, verify_chain
from apps.core.forms import SchemaForm
from apps.core.models import AuditLog
from apps.core.registry import registry
from apps.events import rbac, services
from apps.events.models import Membership, Role, RoleAssignment

from . import forms
from .shortcuts import event_view, superuser_view

User = get_user_model()


# --------------------------------------------------------------------------- members

@event_view("events.members")
def members(request, slug, *, event):
    rbac.require(request, event, "events.members")
    form = forms.InviteForm(request.POST or None, event=event)
    if request.method == "POST" and form.is_valid():
        role = form.cleaned_data["role"]
        if role.grants_sensitive and not rbac.has_perm(request.user, event, "events.roles", request=request):
            raise PermissionDenied("events.roles")
        kind, sid = form.scope_parts()
        email = form.cleaned_data["email"].lower()
        user = User.objects.filter(email__iexact=email).first()
        try:
            if user is not None:
                services.assign_role(event, user, role, scope_kind=kind, scope_id=sid, actor=request.user,
                                     request=request)
                messages.success(request, _("%(email)s now has the role %(role)s.") % {"email": email, "role": role})
            else:
                _inv, url = services.invite(event, email, role, actor=request.user, request=request,
                                            scope_kind=kind, scope_id=sid)
                messages.success(request, _("Invitation sent to %(email)s.") % {"email": email})
                request.session["evac_last_invite_url"] = url
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        return redirect("portal:members", slug)
    rows = (Membership.objects.filter(event=event).select_related("user")
            .prefetch_related("assignments__role").order_by("user__email"))
    return render(request, "portal/members.html", {
        "event": event, "members": rows, "form": form,
        "invitations": event.invitations.filter(accepted_at__isnull=True, expires_at__gt=timezone.now()),
        "last_invite_url": request.session.pop("evac_last_invite_url", None),
    })


@require_POST
@event_view("events.members")
def member_action(request, slug, *, event):
    rbac.require(request, event, "events.members")
    try:
        if "remove_assignment" in request.POST:
            ra = get_object_or_404(RoleAssignment, pk=request.POST["remove_assignment"], membership__event=event)
            if ra.role.grants_sensitive and not rbac.has_perm(request.user, event, "events.roles", request=request):
                raise PermissionDenied("events.roles")
            services.unassign_role(ra, actor=request.user, request=request)
        elif "remove_member" in request.POST:
            m = get_object_or_404(Membership, pk=request.POST["remove_member"], event=event)
            if any(a.role.grants_sensitive for a in m.assignments.select_related("role")) and not rbac.has_perm(
                    request.user, event, "events.roles", request=request):
                raise PermissionDenied("events.roles")
            services.remove_member(m, actor=request.user, request=request)
        elif "revoke_invitation" in request.POST:
            inv = get_object_or_404(event.invitations, pk=request.POST["revoke_invitation"])
            log(action="member.invitation_revoked", actor=request.user, target=inv, event=event, request=request)
            inv.delete()
        messages.success(request, _("Done."))
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("portal:members", slug)


# --------------------------------------------------------------------------- roles

@event_view("events.members")
def roles(request, slug, *, event):
    rows = []
    for role in event.roles.all():
        rows.append({"role": role, "count": role.assignments.count(), "effective": sorted(role.expanded()),
                     "sensitive": role.grants_sensitive})
    return render(request, "portal/roles.html", {
        "event": event, "rows": rows,
        "can_edit": rbac.has_perm(request.user, event, "events.roles", request=request),
    })


@event_view("events.members")
def role_edit(request, slug, key=None, *, event):
    rbac.require(request, event, "events.roles")
    role = get_object_or_404(Role, event=event, key=key) if key else Role(event=event)
    before = {"name": role.name, "permissions": list(role.permissions or []), "require_2fa": role.require_2fa}
    form = forms.RoleForm(request.POST or None, instance=role)
    if request.method == "POST":
        if "delete" in request.POST and role.pk:
            if role.builtin:
                messages.error(request, _("Built-in roles cannot be deleted."))
            elif role.assignments.exists():
                messages.error(request, _("Remove this role from all members first."))
            else:
                log(action="role.deleted", actor=request.user, target=role, event=event, request=request)
                role.delete()
                messages.success(request, _("Role deleted."))
                return redirect("portal:roles", slug)
        elif form.is_valid():
            obj = form.save(commit=False)
            obj.event = event
            obj.permissions = form.permission_list()
            try:
                services.save_role(obj, actor=request.user, request=request, before=before)
            except ValidationError as exc:
                for msg in exc.messages:
                    form.add_error(None, msg)
            else:
                if obj.grants_sensitive and not obj.require_2fa:
                    messages.warning(request, _("This role grants alarm-relevant permissions but does not require "
                                                "two-factor authentication. Those permissions still only work in a "
                                                "two-factor verified session."))
                messages.success(request, _("Role saved."))
                return redirect("portal:roles", slug)
    return render(request, "portal/role_form.html", {"event": event, "form": form, "role": role})


# --------------------------------------------------------------------------- modules

def _toggle(request, event=None):
    form = forms.ModuleToggleForm(request.POST)
    if not form.is_valid() or form.cleaned_data["key"] not in registry.ensure_loaded().modules:
        raise Http404
    key, value = form.cleaned_data["key"], form.cleaned_data["value"]
    try:
        if event is None:
            modules.set_instance(key, value == "on", user=request.user, request=request)
        else:
            modules.set_event(event, key, None if value == "inherit" else value == "on", user=request.user,
                              request=request)
        from apps.core.webhooks import emit

        emit("module.toggled", {"module": key, "value": value, "level": "event" if event else "instance"},
             event=event)
    except ValueError as exc:
        messages.error(request, str(exc))


@superuser_view
def instance_modules(request):
    if request.method == "POST":
        _toggle(request)
        return redirect("portal:instance_modules")
    return render(request, "portal/modules.html", {"rows": modules.status(), "level": "instance"})


@event_view("modules.manage")
def event_modules(request, slug, *, event):
    rbac.require(request, event, "modules.manage")
    if request.method == "POST":
        _toggle(request, event)
        return redirect("portal:event_modules", slug)
    return render(request, "portal/modules.html", {"rows": modules.status(event), "level": "event", "event": event})


# --------------------------------------------------------------------------- settings namespaces

def _settings_page(request, ns_key, level, scope_id, *, event=None, back=None):
    ns = registry.ensure_loaded().settings_namespaces.get(ns_key)
    if ns is None or level not in ns.levels:
        raise Http404
    stored = settings_store.raw(ns_key, level, scope_id)
    resolved = settings_store.resolve(ns_key, event=event)
    inherit = level != "instance"
    form = SchemaForm(request.POST or None, schema=dict(ns.schema), initial_values=stored, inherit=inherit,
                      resolved=resolved, level=level)
    if request.method == "POST" and form.is_valid():
        try:
            settings_store.save(ns_key, level, scope_id, form.values(), user=request.user, event=event,
                                request=request)
        except settings_store.SettingsError as exc:
            for err in exc.errors:
                form.add_error(None, err)
        else:
            messages.success(request, _("Settings saved."))
            return redirect(request.path)
    return render(request, "portal/settings_ns.html", {"ns": ns, "form": form, "level": level, "event": event,
                                                       "back": back, "stored": stored})


@superuser_view
def instance_settings(request):
    namespaces = sorted((ns for ns in registry.ensure_loaded().settings_namespaces.values()
                         if "instance" in ns.levels), key=lambda n: n.order)
    return render(request, "portal/instance_settings.html", {"namespaces": namespaces})


@superuser_view
def instance_settings_ns(request, ns):
    return _settings_page(request, ns, "instance", "")


@event_view("settings.manage")
def event_settings_ns(request, slug, ns, *, event):
    spec = registry.ensure_loaded().settings_namespaces.get(ns)
    if spec is None:
        raise Http404
    rbac.require(request, event, spec.permission)
    return _settings_page(request, ns, "event", str(event.pk), event=event, back=("portal:event_settings", slug))


# --------------------------------------------------------------------------- audit

def _audit_filtered(request, qs):
    q = request.GET
    if q.get("action"):
        qs = qs.filter(action__startswith=q["action"])
    if q.get("actor"):
        qs = qs.filter(actor_repr__icontains=q["actor"])
    if q.get("q"):
        qs = qs.filter(message__icontains=q["q"]) | qs.filter(target_repr__icontains=q["q"])
    if q.get("drill") in ("0", "1"):
        qs = qs.filter(drill=q["drill"] == "1")
    return qs


def _audit_response(request, qs, name, context):
    fmt = request.GET.get("format")
    if fmt in ("csv", "json"):
        log(action="audit.exported", actor=request.user, event=context.get("event"), request=request,
            message=f"Audit log exported as {fmt}")
        if fmt == "csv":
            resp = HttpResponse(export_csv(qs), content_type="text/csv; charset=utf-8")
        else:
            resp = JsonResponse({"entries": export_rows(qs)}, json_dumps_params={"indent": 1, "default": str})
        resp["Content-Disposition"] = f'attachment; filename="{name}.{fmt}"'
        return resp
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "portal/audit.html", {**context, "page": page, "filters": request.GET})


@event_view("audit.view")
def audit(request, slug, *, event):
    rbac.require(request, event, "audit.view")
    if request.GET.get("format"):
        rbac.require(request, event, "audit.export")
    qs = _audit_filtered(request, AuditLog.objects.for_event(event))
    return _audit_response(request, qs, f"evac-audit-{event.slug}", {"event": event})


@superuser_view
def instance_audit(request):
    verify = None
    if request.GET.get("verify"):
        verify = verify_chain()
        log(action="audit.verified", actor=request.user, request=request,
            message=f"Audit chain {'OK' if verify.ok else 'BROKEN'} ({verify.checked} rows)")
    qs = _audit_filtered(request, AuditLog.objects.all())
    return _audit_response(request, qs, "evac-audit", {"verify": verify, "instance": True})


# --------------------------------------------------------------------------- event tokens

@event_view("tokens.manage")
def event_tokens(request, slug, *, event):
    rbac.require(request, event, "tokens.manage")
    form = TokenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        issue_token_from_form(request, form, event=event)
        messages.warning(request, _("Copy the token now - it will not be shown again."))
        return redirect("portal:event_tokens", slug)
    return render(request, "portal/event_tokens.html", {
        "event": event, "form": form, "tokens": request.user.service_tokens.filter(event=event),
        "new_token": request.session.pop("evac_new_token", None)})


# --------------------------------------------------------------------------- users (instance admin)

@superuser_view
def users(request):
    q = (request.GET.get("q") or "").strip()
    qs = User.objects.all().order_by("email")
    if q:
        qs = qs.filter(email__icontains=q) | qs.filter(display_name__icontains=q)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "portal/users.html", {"page": page, "q": q})


@require_POST
@superuser_view
def user_action(request, pk):
    from apps.accounts import twofactor

    user = get_object_or_404(User, pk=pk)
    action = request.POST.get("action")
    if user == request.user and action in ("deactivate", "demote"):
        messages.error(request, _("You cannot do this to your own account."))
        return redirect("portal:users")
    if action == "reset_2fa":
        twofactor.remove_all(user, actor=request.user)
    elif action in ("activate", "deactivate"):
        user.is_active = action == "activate"
        user.save(update_fields=["is_active"])
        log(action=f"account.{action}d", actor=request.user, target=user, request=request)
    elif action in ("promote", "demote"):
        user.is_superuser = user.is_staff = action == "promote"
        user.save(update_fields=["is_superuser", "is_staff"])
        log(action="account.instance_admin", actor=request.user, target=user, request=request,
            changes={"is_superuser": [not user.is_superuser, user.is_superuser]})
    else:
        raise Http404
    messages.success(request, _("Done."))
    return redirect("portal:users")
