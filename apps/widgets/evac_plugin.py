# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    ModuleSpec,
    NavEntry,
    PackSectionSpec,
    PermissionSpec,
    PluginManifest,
    SettingsNamespace,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="widgets", name="Data feeds and custom widgets", version="0.1.0", kind="module")


def register(r: Registry) -> None:
    from . import packs, services

    r.module(ModuleSpec(key="widgets", name=str(_("Custom widgets")), order=36, category="screens",
                        depends_on=("content",),
                        description=str(_("Show data on screens without code: JSON, RSS, iCal or CSV feeds and EVAC "
                                          "data sources, mapped to lists, tables, cards, counters, gauges, tickers "
                                          "and charts."))))
    r.permissions_([
        PermissionSpec("widgets.view", str(_("See data feeds and custom widgets"))),
        PermissionSpec("widgets.edit", str(_("Add and change data feeds and custom widgets"))),
    ])
    r.nav(NavEntry(module="widgets", label=str(_("Data & widgets")), url_name="widgets:index",
                   permission="widgets.view", section="content", order=25))
    r.settings_namespace(SettingsNamespace(
        key="widgets", title=str(_("Data feeds")), module="widgets", levels=("instance",), order=36,
        schema={"type": "object", "properties": {
            "allow_private_networks": {
                "type": "boolean", "title": "Allow feeds from private networks", "default": False,
                "description": "Lets event staff fetch URLs in local networks (e.g. sensors at the venue). Leave off "
                               "on servers that can reach internal systems."},
        }}))
    r.editor_choices("dataWidgets", services.editor_choices, module="widgets")
    r.editor_choices("widgetData", services.event_payload, module="widgets")
    r.pack_section(PackSectionSpec(key="feeds", title=str(_("Data feeds")), module="widgets", order=40,
                                   choices=packs.feed_choices, dump=packs.dump_feeds, load=packs.load_feeds))
    r.pack_section(PackSectionSpec(key="widgets", title=str(_("Custom widgets")), module="widgets", order=50,
                                   choices=packs.widget_choices, requires=packs.widget_requires,
                                   dump=packs.dump_widgets, load=packs.load_widgets))
