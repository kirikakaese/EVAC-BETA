# SPDX-License-Identifier: AGPL-3.0-or-later
"""“Sync now” below Settings → Extensions → pretalx / frab / iCal."""
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.extensions.views import config_for_custom_view


@require_POST
def sync_now(request, key, slug=None):
    from . import importer

    event, config = config_for_custom_view(request, key, slug)
    if event is None:
        return redirect("extensions:instance_index")
    importer.queue(config, reason=f"manual:{request.user.pk}")
    messages.success(request, _("Sync started; the result appears in the log below."))
    return redirect(reverse("extensions:event_detail", args=[event.slug, key]))


def index(request, key, slug=None):
    if slug is None:
        return redirect("extensions:instance_index")
    return redirect("schedule:index", slug)


urlpatterns = [path("", index, name="index"), path("sync/", sync_now, name="sync")]
