# SPDX-License-Identifier: AGPL-3.0-or-later
"""Custom views of the webhooks extension: manage outbound endpoints and inspect deliveries."""
from __future__ import annotations

import secrets

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.core import crypto
from apps.core.audit import log
from apps.core.registry import registry
from apps.extensions.views import config_for_custom_view

from .models import WebhookEndpoint


class EndpointForm(forms.ModelForm):
    event_types = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple,
                                            label=gettext_lazy("Event types"),
                                            help_text=gettext_lazy("Leave all unticked to receive every event type."))

    class Meta:
        model = WebhookEndpoint
        fields = ["name", "url", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_types"].choices = [(k, f"{k} - {s.description}") for k, s in
                                              sorted(registry.ensure_loaded().webhook_events.items())]
        if self.instance.pk:
            self.fields["event_types"].initial = self.instance.event_types


def _back(event, key):
    if event is None:
        return reverse("extensions:instance_webhooks:endpoints")
    return reverse("extensions:event_webhooks:endpoints", args=[event.slug])


def endpoints(request, key, slug=None):
    event, config = config_for_custom_view(request, key, slug)
    form = EndpointForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ep = form.save(commit=False)
        ep.config = config
        ep.event_types = form.cleaned_data["event_types"]
        raw = "whsec_" + secrets.token_urlsafe(24)
        ep.secret_encrypted = crypto.encrypt(raw)
        ep.save()
        log(action="extension.webhook_endpoint_added", actor=request.user, target=ep, event=event, request=request,
            message=f"Webhook endpoint {ep.name} -> {ep.url}")
        request.session[f"epsecret:{ep.pk}"] = raw
        messages.warning(request, _("Endpoint added. Copy its signing secret now - it will not be shown again."))
        return redirect(_back(event, key))
    items = []
    for ep in config.webhook_endpoints.all():
        items.append({"ep": ep, "secret": request.session.pop(f"epsecret:{ep.pk}", None),
                      "attempts": ep.attempts.all()[:10]})
    return render(request, "webhooks/endpoints.html", {
        "event": event, "config": config, "form": form, "items": items, "key": key,
        "inbound": config.inbound_events.all()[:20],
        "settings_url": reverse("extensions:instance_detail", args=[key]) if event is None
        else reverse("extensions:event_detail", args=[event.slug, key]),
    })


@require_POST
def endpoint_delete(request, key, pk, slug=None):
    event, config = config_for_custom_view(request, key, slug)
    ep = get_object_or_404(WebhookEndpoint, pk=pk, config=config)
    log(action="extension.webhook_endpoint_removed", actor=request.user, target=ep, event=event, request=request,
        message=f"Webhook endpoint {ep.name} removed")
    ep.delete()
    messages.success(request, _("Endpoint removed."))
    return redirect(_back(event, key))
