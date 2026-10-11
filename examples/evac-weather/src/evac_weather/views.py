# SPDX-License-Identifier: AGPL-3.0-or-later
"""The extension page below Settings -> Extensions -> Weather: readings, enter one, fetch now."""
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.extensions.views import config_for_custom_view

from . import services, tasks
from .models import Observation


class ObservationForm(forms.Form):
    temperature_c = forms.FloatField(label=gettext_lazy("Temperature (°C)"), min_value=-60, max_value=60)
    condition = forms.CharField(label=gettext_lazy("Conditions"), max_length=80,
                                help_text=gettext_lazy("For example: Light rain"))
    wind_kmh = forms.FloatField(label=gettext_lazy("Wind (km/h)"), min_value=0, max_value=400, required=False)


def _event_config(request, key, slug):
    event, config = config_for_custom_view(request, key, slug)
    if event is None:  # the extension is per event
        raise Http404
    return event, config


def index(request, key, slug=None):
    event, config = _event_config(request, key, slug)
    form = ObservationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.record(event, **form.cleaned_data, actor=request.user, request=request)
        messages.success(request, _("Reading saved; screens show it within a minute."))
        return redirect(reverse("extensions:event_weather:index", args=[event.slug]))
    return render(request, "evac_weather/index.html", {
        "event": event, "config": config, "form": form,
        "observations": Observation.objects.filter(event=event).select_related("created_by")[:20],
        "payload": services.current(event),
        "settings_url": reverse("extensions:event_detail", args=[event.slug, key]),
    })


@require_POST
def fetch_now(request, key, slug=None):
    event, config = _event_config(request, key, slug)
    if not config.settings.get("online"):
        messages.error(request, _("Switch on “Fetch from Open-Meteo” in the settings first."))
    else:
        tasks.fetch.delay(str(config.pk), str(event.pk))
        messages.success(request, _("Fetching; the result appears below in a moment."))
    return redirect(reverse("extensions:event_weather:index", args=[event.slug]))
