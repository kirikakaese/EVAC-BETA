# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    EventHook,
    ModuleSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    ScopeKind,
    SettingsNamespace,
    SetupCheckSpec,
    SetupResult,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="venues", name="Venues", version="0.1.0", kind="module")


def _venue_choices(event):
    return [(str(v.pk), v.name) for v in event.venues.all()]


def _zone_choices(event):
    from .models import Zone

    return [(str(z.pk), f"{z.venue.name} · {z.name}") for z in Zone.objects.filter(venue__events=event)
            .select_related("venue")]


def _room_choices(event):
    from .models import Room

    return [(str(r.pk), f"{r.venue.name} · {r.name}") for r in Room.objects.filter(venue__events=event)
            .select_related("venue")]


def _assembly_choices(event):
    from .models import Point

    return [(str(p.pk), f"{p.venue.name} · {p.name}") for p in Point.objects.filter(
        venue__events=event, kind=Point.Kind.ASSEMBLY).select_related("venue")]


def _venue_check(event, request):
    """Setup checklist: the event takes place somewhere."""
    return "done" if event.venues.exists() else "todo"


def _map_check(event, request):
    """Setup checklist: every venue of the event has zones and at least one exit (routes and evacuation need them)."""
    from django.db.models import Count, Q
    from django.urls import reverse

    from .models import Point, Venue

    rows = list(Venue.objects.filter(events=event).annotate(
        n_zones=Count("zones", distinct=True),
        n_exits=Count("points", filter=Q(points__kind=Point.Kind.EXIT), distinct=True)).order_by("name"))
    if not rows:
        return None
    lacking = [v for v in rows if not v.n_zones or not v.n_exits]
    if not lacking:
        return "done"
    v = lacking[0]
    what = (_("no zones and no exits") if not v.n_zones and not v.n_exits
            else _("no zones") if not v.n_zones else _("no exits"))
    return SetupResult("todo", detail=f"{v.name}: {what}", url=reverse("venues:map", args=[event.slug, v.slug]))


def register(r: Registry) -> None:
    from . import sync as node_sync

    r.sync(node_sync.spec())
    from . import transfer

    r.module(ModuleSpec(key="venues", name=str(_("Venues")), order=10, category="venue",
                        description=str(_("Buildings, floors, rooms and zones; reusable across events. "
                                          "Exits, assembly points, waypoints and the route graph."))))
    r.permissions_([
        PermissionSpec("venues.view", str(_("See venues, rooms and zones")), scopes=("venue",)),
        PermissionSpec("venues.manage", str(_("Edit venues, rooms and zones")), scopes=("venue",)),
    ])
    r.setup_check(SetupCheckSpec(
        key="venue", label=str(_("Link a venue")), check=_venue_check, module="venues", order=10,
        url_name="venues:index", help=str(_("Where the event takes place; venues are shared between events."))))
    r.setup_check(SetupCheckSpec(
        key="venue_map", label=str(_("Draw zones and exits")), check=_map_check, module="venues", order=20,
        url_name="venues:index", help=str(_("Zones target announcements and alarms; exits make routes possible."))))
    r.scope_kind(ScopeKind(key="venue", label=str(_("Venue")), choices=_venue_choices, module="venues"))
    r.scope_kind(ScopeKind(key="zone", label=str(_("Zone")), choices=_zone_choices, module="venues"))
    r.scope_kind(ScopeKind(key="room", label=str(_("Room")), choices=_room_choices, module="venues"))
    r.scope_kind(ScopeKind(key="assembly", label=str(_("Assembly point")), choices=_assembly_choices,
                           module="venues"))
    r.nav(NavEntry(module="venues", label=str(_("Venues")), url_name="venues:index", permission="venues.view",
                   section="event", order=20))
    r.event_hook(EventHook(module="venues", export=transfer.export_venues, import_=transfer.import_venues,
                           order=10))
    r.settings_namespace(SettingsNamespace(
        key="maps", title=str(_("Maps")), module="venues", levels=("instance",), order=12,
        schema={"type": "object", "properties": {
            "tiles_enabled": {"type": "boolean", "title": "Show map tiles under floor plans and outdoor sites",
                              "default": True},
            "tile_url": {"type": "string", "title": "Tile server", "maxLength": 300,
                         "default": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                         "description": "URL template with {z}, {x}, {y} (and optionally {s}). Tiles are cached "
                                        "on this server when someone views them."},
            "attribution": {"type": "string", "title": "Attribution", "maxLength": 200,
                            "default": "© OpenStreetMap contributors"},
            "allow_area_download": {"type": "boolean", "title": "Allow downloading map areas for offline use",
                                    "default": False,
                                    "description": "Only for a tile server you run yourself: the public "
                                                   "OpenStreetMap servers forbid bulk downloads (refused)."},
            "max_zoom": {"type": "integer", "title": "Highest zoom level", "default": 19, "minimum": 10,
                         "maximum": 20},
        }}))
