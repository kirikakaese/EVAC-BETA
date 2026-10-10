# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demo data so everything is clickable on a laptop (all content English).

Creates (idempotently) an instance admin ``admin@evac.local`` / ``evac-demo-admin``, a demo venue with
buildings, floors, rooms and zones, the event ``demo`` with members in every built-in role and a scoped
role assignment, a webhook extension config and a few audit entries. Screens, themes, layouts, schedule,
crew and announcements are added by their modules' seeds in later phases (see docs/ROADMAP.md).
"""
import datetime as dt

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.events import services
from apps.events.models import Event
from apps.venues.models import Building, Floor, Room, Venue, Zone

DEMO_PASSWORD = "evac-demo-admin"
PEOPLE = [
    ("orga@evac.local", "Olivia Orga", "orga"),
    ("control@evac.local", "Carl Control", "control-room"),
    ("security@evac.local", "Sam Security", "security"),
    ("helpdesk@evac.local", "Hana Helpdesk", "helpdesk"),
    ("crew@evac.local", "Chris Crew", "crew"),
    ("viewer@evac.local", "Vic Viewer", "viewer"),
]


class Command(BaseCommand):
    help = "Create demo data (idempotent). Also run by the container entrypoint when EVAC_SEED_DEMO=1."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=DEMO_PASSWORD, help="Password for all demo accounts.")

    @transaction.atomic
    def handle(self, *args, password, **opts):
        admin = User.objects.filter(email="admin@evac.local").first()
        if admin is None:
            admin = User.objects.create_superuser(email="admin@evac.local", password=password,
                                                  display_name="Demo Admin")
        venue, created = Venue.objects.get_or_create(slug="demo-hall", defaults={
            "name": "Demo Exhibition Hall", "timezone": "Europe/Berlin", "is_permanent": True,
            "address": "1 Example Street\n12345 Sample City", "latitude": "52.520008", "longitude": "13.404954",
            "description": "A permanent venue with two halls, a foyer and an open-air area."})
        if created:
            main = Building.objects.create(venue=venue, name="Main building", order=1)
            outdoor = Building.objects.create(venue=venue, name="Open-air site", outdoor=True, order=2)
            ground = Floor.objects.create(building=main, name="Ground floor", level=0)
            upper = Floor.objects.create(building=main, name="First floor", level=1)
            Floor.objects.create(building=outdoor, name="Field", level=0)
            # zone outlines in metres on the ground floor (the map editor draws them on a plan)
            gf = str(ground.pk)
            north = Zone.objects.create(venue=venue, name="Zone North", capacity=1200, color="#2563eb",
                                        areas=[{"floor": gf, "points": [[0, 0], [60, 0], [60, 30], [0, 30]]}])
            south = Zone.objects.create(venue=venue, name="Zone South", capacity=900, color="#16a34a",
                                        areas=[{"floor": gf, "points": [[0, 30], [60, 30], [60, 55], [0, 55]]}])
            yard = Zone.objects.create(venue=venue, name="Courtyard", outdoor=True, capacity=2000, color="#ca8a04",
                                       areas=[{"floor": gf, "points": [[60, 0], [95, 0], [95, 55], [60, 55]]}])
            rooms = [("Hall A", ground, [north], 800), ("Hall B", ground, [south], 600), ("Foyer", ground,
                     [north, south], 300), ("Workshop 1", upper, [north], 40), ("Workshop 2", upper, [south], 40)]
            for name, floor, zones, cap in rooms:
                room = Room.objects.create(venue=venue, floor=floor, name=name, capacity=cap,
                                           has_lift=floor == upper, wheelchair_spaces=4 if cap > 100 else 1)
                room.zones.set(zones)
            Room.objects.create(venue=venue, name="Beer garden", capacity=500).zones.set([yard])
        event = Event.objects.filter(slug="demo").first()
        if event is None:
            today = timezone.localdate()
            event = services.create_event(name="Demo Festival", slug="demo", user=admin, timezone="Europe/Berlin",
                                          start_date=today, end_date=today + dt.timedelta(days=3),
                                          description="A three-day demo event to try EVAC.",
                                          primary_color="#15803d", accent_color="#22d3ee")
            event.venues.add(venue)
            event.transition("setup", user=admin, reason="Demo seed")
        for email, name, role_key in PEOPLE:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password=password, display_name=name,
                                                email_verified=True)
            services.assign_role(event, user, event.roles.get(key=role_key), actor=admin)
        # a scoped grant: the crew member may also see venue details only for Zone North
        crew = User.objects.get(email="crew@evac.local")
        north = Zone.objects.filter(venue=venue, name="Zone North").first()
        if north is not None:
            services.assign_role(event, crew, event.roles.get(key="viewer"), scope_kind="zone",
                                 scope_id=str(north.pk), actor=admin)
        # the demo shows the (otherwise off by default) evacuation module
        from apps.core import modules
        from apps.core.registry import registry

        if "evacuation" in registry.ensure_loaded().modules and not modules.instance_enabled("evacuation"):
            modules.set_instance("evacuation", True, user=admin)
        # a demo program (when the program module is installed): sessions today and tomorrow
        import importlib

        # demo data of optional modules, when installed (they are never imported directly)
        for key, path in (("program", "apps.schedule.demo"), ("crowd", "apps.crowd.demo"), ("ops", "apps.ops.demo")):
            if key in registry.modules:
                importlib.import_module(path).seed(event, admin)
        self.stdout.write(self.style.SUCCESS(
            f"Demo ready: log in as admin@evac.local / {password} (other demo accounts: "
            f"{', '.join(p[0] for p in PEOPLE)}; same password). Event: /e/demo/"))
