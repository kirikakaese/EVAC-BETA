# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import re_path

from . import views

app_name = "content_files"
urlpatterns = [re_path(r"^files/(?P<sha>[0-9a-f]{64})/(?P<name>[a-z0-9][a-z0-9_.-]{0,60})$", views.file,
                       name="file")]
