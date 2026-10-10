# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import api

app_name = "node_api"
urlpatterns = [
    path("enrol/", api.enrol, name="enrol"),
    path("events/", api.events, name="events"),
    path("events/<uuid:event_id>/snapshot/", api.snapshot_view, name="snapshot"),
    path("events/<uuid:event_id>/snapshot/confirm/", api.snapshot_confirm, name="snapshot_confirm"),
    path("events/<uuid:event_id>/files/<path:path>", api.file_view, name="file"),
    path("events/<uuid:event_id>/oplog/", api.oplog, name="oplog"),
    path("events/<uuid:event_id>/actions/", api.actions, name="actions"),
    path("events/<uuid:event_id>/actions/<int:action_id>/", api.action_result, name="action_result"),
    path("events/<uuid:event_id>/checkin/", api.checkin, name="checkin"),
]
