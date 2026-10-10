# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "nodes"
PORTAL_MOUNT = True  # /e/<slug>/nodes/: the event's checkout to a venue node
ROOT_MOUNTS = [("api/v1/node/", "apps.nodes.api_urls", "node_api"),
               ("settings/nodes/", "apps.nodes.admin_urls", "nodes_admin")]
urlpatterns = [
    path("", views.event_node, name="index"),
]
