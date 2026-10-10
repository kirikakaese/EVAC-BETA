# SPDX-License-Identifier: AGPL-3.0-or-later
"""DIAL — DECT & IP Administration Layer (brief §9, roadmap phase 4, ADR-0037).

Each EVAC event links one DIAL event (Settings -> Extensions -> DIAL): emergency calls in DIAL reach the
evacuation trigger policy, alarms ring DIAL handsets, orga record announcements by phone, and DIAL's phonebook,
numbers, info pages and DECT status become data sources for screens. Nothing outside this package imports it.
"""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    DataSourceSpec,
    EvacTriggerSpec,
    ExtensionFeature,
    ExtensionSpec,
    NotificationChannelSpec,
    PermissionSpec,
    PluginManifest,
    WebhookEventSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="dial", name="DIAL", version="1.0.0", kind="extension",
                          description="DECT & IP Administration Layer: emergency calls, handset broadcasts, "
                                      "announcements by phone, phonebook and DECT status.")


def register(r: Registry) -> None:
    from . import inbound, link, outbound, recordings, sources
    from .ops import PERM_STATUS

    r.extension(ExtensionSpec(
        key=link.KEY, name="DIAL", version="1.0.0", scope="event", icon="☎", docs="extensions/dial",
        description=str(_("Link the event's DIAL phone network: emergency calls reach the evacuation triggers, "
                          "alarms ring the handsets, announcements can be recorded by phone, and the phonebook, "
                          "important numbers, info pages and DECT status show on screens.")),
        settings_schema=link.SCHEMA,
        secret_fields=(("token", str(_("DIAL service token (dial_…)"))),),
        features=(
            ExtensionFeature("trigger", str(_("Emergency calls → evacuation trigger")), "trigger",
                             str(_("emergency.triggered from DIAL goes through the trigger policy of source "
                                   "“DIAL”."))),
            ExtensionFeature("evacuation_broadcast", str(_("Alarms ring DIAL handsets")), "channel",
                             str(_("Evacuation stages listed below are announced through DIAL's emergency "
                                   "broadcast."))),
            ExtensionFeature("announcements", str(_("Announcement channels")), "channel",
                             str(_("“DIAL: ring handsets” and “DIAL: DECT message” in the announcement composer."))),
            ExtensionFeature("recordings", str(_("Announcements by phone")), "import",
                             str(_("Recordings made in DIAL become announcements (approval queue)."))),
            ExtensionFeature("data_sources", str(_("Data sources and widgets")), "data_source",
                             str(_("Phonebook, important numbers, info pages and DECT status."))),
        ),
        inbound_webhooks=True, signature_header="X-DIAL-Signature", event_header="X-DIAL-Event",
        delivery_header="X-DIAL-Delivery", delivery_id=inbound.delivery_id,
        test_connection=link.test_connection, handle_webhook=inbound.handle, urls="extensions.dial.settings_urls"))
    r.permissions_([
        PermissionSpec(PERM_STATUS, str(_("See the DIAL link: DECT status, broadcasts, phone recordings"))),
    ])
    r.evac_trigger(EvacTriggerSpec(key=inbound.SOURCE, name=str(_("DIAL emergency call")), module="evacuation",
                                   description=str(_("Someone dialled an emergency number in the linked DIAL "
                                                     "event."))))
    for key, name, desc in [
        ("dial.phonebook", _("DIAL phonebook"), _("Public phonebook entries of the linked DIAL event.")),
        ("dial.numbers", _("DIAL important numbers"), _("“Call X for Y”: own list, emergency and service numbers.")),
        ("dial.pages", _("DIAL info pages"), _("Published info pages of the linked DIAL event (as text).")),
        ("dial.dect", _("DIAL DECT status"), _("Base stations (RFPs), clusters and recent DECT alerts.")),
    ]:
        r.data_source(DataSourceSpec(key=key, name=str(name), description=str(desc), fetch=sources.FETCHERS[key],
                                     module="widgets", ttl_seconds=300))
    r.notification_channel(NotificationChannelSpec(
        key="dial_call", name=str(_("DIAL: ring handsets")), module="announcements",
        send=outbound.channel("emergency"), available=outbound.available, max_length=1000,
        description=str(_("DIAL emergency broadcast: every handset rings and hears the text."))))
    r.notification_channel(NotificationChannelSpec(
        key="dial_sms", name=str(_("DIAL: DECT message")), module="announcements",
        send=outbound.channel("message"), available=outbound.available, max_length=outbound.SMS_LIMIT,
        description=str(_("A text message to the DECT handsets (needs DIAL's messaging feature)."))))
    r.webhook_event(WebhookEventSpec(key="dial.dect_alert", module="dial",
                                     description="DIAL reported a DECT alert (base station down/up, sync degraded)."))
    r.webhook_sink(outbound.sink)
    r.outbox_handler(outbound.JOB, outbound.handle_job)
    r.outbox_handler(inbound.RECORDING_JOB, recordings.handle_job)
    r.outbox_handler(inbound.REFRESH_JOB, sources.handle_refresh)
