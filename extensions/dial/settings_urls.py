# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mounted below Settings -> Extensions -> DIAL ("More"): leads to the DIAL page of the event."""
from django.shortcuts import redirect
from django.urls import path


def to_status(request, key, slug=None):
    if slug is None:
        return redirect("extensions:instance_index")
    return redirect("dial:status", slug)


urlpatterns = [path("", to_status, name="status")]
