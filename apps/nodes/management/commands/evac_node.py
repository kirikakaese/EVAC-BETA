# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = ("Venue node (EVAC_MODE=node, ADR-0036): evac_node enrol --central URL --code CODE [--ca-file F] | "
            "run [--interval 2] | sync | status")

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("action", choices=["enrol", "run", "sync", "status"])
        parser.add_argument("--central", default="")
        parser.add_argument("--code", default="")
        parser.add_argument("--ca-file", default="")
        parser.add_argument("--interval", type=float, default=2.0)
        parser.add_argument("--rounds", type=int, default=0, help="stop after this many rounds (0 = forever)")

    def handle(self, *args: Any, action: str, central: str, code: str, ca_file: str, interval: float, rounds: int,
               **opts: Any) -> None:
        from apps.nodes import client
        from apps.nodes.models import NodeEvent

        if settings.EVAC_MODE != "node":
            raise CommandError("set EVAC_MODE=node on a venue node")
        if action == "enrol":
            if not central or not code:
                raise CommandError("--central and --code are needed")
            try:
                ident = client.enrol(central, code, ca_file=ca_file)
            except (ValueError, client.Unreachable) as err:
                raise CommandError(f"enrolment failed: {err}") from err
            self.stdout.write(f"enrolled as {ident.name} ({ident.node_id}) at {ident.central_url}")
            return
        if client.identity() is None:
            raise CommandError("not enrolled yet: evac_node enrol --central URL --code CODE")
        if action == "sync":
            self.stdout.write(json.dumps(client.sync_once(), default=str, indent=1))
        elif action == "run":
            client.run(interval=interval, rounds=rounds)
        else:
            me = client.identity()
            assert me is not None
            self.stdout.write(f"{me.name} → {me.central_url}; last contact {me.last_contact}"
                              + (f"; {me.last_error}" if me.last_error else ""))
            for ne in NodeEvent.objects.all():
                self.stdout.write(f"  {ne.slug}: {'held' if ne.checked_out else 'read-only copy'}, snapshot "
                                  f"{ne.snapshot_version or '-'}, op-log {ne.pushed_seq}/{ne.next_seq - 1} sent, "
                                  f"{ne.files_missing} files missing")
