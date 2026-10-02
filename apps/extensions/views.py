# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings -> Extensions: card grid and generated per-extension settings pages (instance and event)."""
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import modules
from apps.core.forms import SchemaForm
from apps.core.registry import registry
from apps.events import rbac
from apps.events.models import Event

from . import services
from .models import ExtensionConfig


def resolve(request, key: str | None = None, slug: str | None = None):
    """Return ``(event, spec, config)`` after permission checks. ``config`` may be unsaved."""
    if not request.user.is_authenticated:
        raise PermissionDenied
    event = None
    if slug is not None:
        event = get_object_or_404(Event, slug=slug)
        request.event = event
        rbac.require(request, event, "extensions.manage")
        if not modules.is_enabled("extensions", event):
            raise Http404("Extensions are switched off for this event")
    elif not request.user.is_superuser:
        raise PermissionDenied
    if key is None:
        return event, None, None
    spec = registry.get_extension(key)
    if spec is None or spec not in services.specs_for("event" if event else "instance"):
        raise Http404
    return event, spec, services.get_or_new(spec, event)


def _urls(event, key=None):
    if event is None:
        return {"index": reverse("extensions:instance_index"),
                "detail": reverse("extensions:instance_detail", args=[key]) if key else ""}
    return {"index": reverse("extensions:event_index", args=[event.slug]),
            "detail": reverse("extensions:event_detail", args=[event.slug, key]) if key else ""}


@login_required
def index(request, slug=None):
    event, _spec, _cfg = resolve(request, slug=slug)
    cards = []
    for spec in services.specs_for("event" if event else "instance"):
        cards.append({"spec": spec, "status": services.card_status(spec, event),
                      "url": _urls(event, spec.key)["detail"],
                      "instance_only": spec.scope == "instance"})
    return render(request, "extensions/index.html", {"event": event, "cards": cards,
                                                     "level": "event" if event else "instance"})


class ConfigForm(forms.Form):
    enabled = forms.BooleanField(required=False, label=_("Enabled"))


def _secret_form(spec, data=None):
    f = forms.Form(data)
    for name, label in spec.secret_fields:
        f.fields[f"secret__{name}"] = forms.CharField(
            label=label, required=False, widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
            help_text=_("Stored encrypted. Leave blank to keep the stored value."))
        f.fields[f"clear__{name}"] = forms.BooleanField(label=_("Remove stored %(label)s") % {"label": label},
                                                        required=False)
    return f


def _feature_form(spec, config, data=None):
    f = forms.Form(data)
    for feat in spec.features:
        f.fields[f"feature__{feat.key}"] = forms.BooleanField(
            label=feat.name, required=False, help_text=feat.description,
            initial=config.features.get(feat.key, feat.default_enabled))
    return f


@login_required
def detail(request, key, slug=None):
    event, spec, config = resolve(request, key, slug)
    inst = services.instance_config(spec.key) if event is not None else None
    can_inherit = event is not None and spec.scope in ("instance", "both")
    if request.method == "POST":
        base = ConfigForm(request.POST)
        use_instance = can_inherit and request.POST.get("use_instance") == "1"
        schema_form = SchemaForm(request.POST, schema=dict(spec.settings_schema),
                                 initial_values=config.settings, prefix="s")
        secret_form = _secret_form(spec, request.POST)
        feature_form = _feature_form(spec, config, request.POST)
        valid = base.is_valid() and secret_form.is_valid() and feature_form.is_valid()
        valid = (schema_form.is_valid() or use_instance) and valid
        if valid:
            secrets = {}
            for name, _label in spec.secret_fields:
                if secret_form.cleaned_data.get(f"clear__{name}"):
                    secrets[name] = "__clear__"
                else:
                    secrets[name] = secret_form.cleaned_data.get(f"secret__{name}", "")
            try:
                services.save_config(
                    config, settings_values=schema_form.values() if not use_instance else {},
                    secret_values=secrets, enabled=base.cleaned_data["enabled"], use_instance=use_instance,
                    features={f.key: feature_form.cleaned_data.get(f"feature__{f.key}", False) for f in spec.features},
                    user=request.user, request=request)
            except services.ExtensionError as exc:
                for err in exc.errors:
                    messages.error(request, err)
            else:
                messages.success(request, _("%(name)s settings saved.") % {"name": spec.name})
                return redirect(_urls(event, spec.key)["detail"])
    else:
        base = ConfigForm(initial={"enabled": config.enabled})
        schema_form = SchemaForm(schema=dict(spec.settings_schema), initial_values=config.settings, prefix="s")
        secret_form = _secret_form(spec)
        feature_form = _feature_form(spec, config)
    stored_secrets = set(config.secrets) if config.is_saved else set()
    webhook_url = ""
    if spec.inbound_webhooks and config.is_saved:
        webhook_url = request.build_absolute_uri(reverse("api:extension-webhook", args=[spec.key, config.pk]))
    return render(request, "extensions/detail.html", {
        "event": event, "spec": spec, "config": config, "base_form": base, "schema_form": schema_form,
        "secret_form": secret_form, "feature_form": feature_form, "stored_secrets": stored_secrets,
        "secret_rows": [(secret_form[f"secret__{n}"], secret_form[f"clear__{n}"], n in stored_secrets)
                        for n, _l in spec.secret_fields],
        "webhook_url": webhook_url, "has_webhook_secret": bool(config.webhook_secret_encrypted),
        "logs": config.logs.all()[:30] if config.is_saved else [], "urls": _urls(event, spec.key),
        "can_inherit": can_inherit, "instance_config": inst,
        "new_webhook_secret": request.session.pop(f"whsecret:{config.pk}", None) if config.is_saved else None,
    })


@login_required
@require_POST
def test(request, key, slug=None):
    event, spec, config = resolve(request, key, slug)
    if not config.is_saved:
        messages.error(request, _("Save the settings first."))
        return redirect(_urls(event, key)["detail"])
    target = config
    if config.use_instance:
        target = services.instance_config(key) or config
    result = services.test_connection(target, user=request.user, request=request)
    if request.headers.get("HX-Request"):
        return render(request, "extensions/_test_result.html", {"result": result})
    (messages.success if result.ok else messages.error)(request, result.message or _("Connection OK."))
    return redirect(_urls(event, key)["detail"])


@login_required
@require_POST
def webhook_secret(request, key, slug=None):
    event, spec, config = resolve(request, key, slug)
    if not config.is_saved or not spec.inbound_webhooks:
        raise Http404
    raw = services.regenerate_webhook_secret(config, user=request.user, request=request)
    request.session[f"whsecret:{config.pk}"] = raw
    messages.warning(request, _("New webhook secret generated. Copy it now - it will not be shown again."))
    return redirect(_urls(event, key)["detail"])


@login_required
@require_POST
def disconnect(request, key, slug=None):
    event, spec, config = resolve(request, key, slug)
    if config.is_saved:
        services.disconnect(config, user=request.user, request=request)
        messages.success(request, _("%(name)s disconnected; its data was purged.") % {"name": spec.name})
    return redirect(_urls(event)["index"])


def config_for_custom_view(request, key, slug=None) -> tuple[Event | None, ExtensionConfig]:
    """Helper for extensions' custom views: permission-checked, saved config (404 when not saved yet)."""
    event, spec, config = resolve(request, key, slug)
    if not config.is_saved:
        raise Http404
    return event, config
