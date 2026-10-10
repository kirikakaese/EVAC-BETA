# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persisted state, scopes, drills, permissions and the audit trail (ADR-0029)."""
from datetime import timedelta
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.accounts.models import User
from apps.core import settings_store
from apps.core.models import AuditLog
from apps.evacuation import machine, services
from apps.evacuation.machine import Refused, State
from apps.evacuation.models import EvacState, StateChange
from apps.events import services as event_services
from apps.venues.models import Venue, Zone

from .conftest import tf


def person(event, role, email, **scope):
    u = User.objects.create_user(email=email, password="pw-12345678x")
    event_services.assign_role(event, u, role, **scope)
    return u


def test_event_and_zone_states_persist(event, admin, zones):
    north = zones["North"]
    services.change(event, "attention", actor=admin, request=tf(admin), reason="smoke reported")
    services.change(event, State.EVACUATE, zone=north, actor=admin, request=tf(admin))
    ev, by_zone = services.statuses(event)
    assert ev.state is State.ATTENTION and by_zone[str(north.pk)].state is State.EVACUATE
    # highest severity wins per screen location
    assert services.effective_for(event, [str(north.pk)]).state is State.EVACUATE
    assert services.effective_for(event, [str(zones["South"].pk)]).state is State.ATTENTION
    assert services.effective_for(event, []).state is State.ATTENTION
    row = EvacState.objects.get(event=event, zone=None)
    assert row.version == 1 and row.reason == "smoke reported" and row.changed_by == admin
    assert "whole event" in str(row) and "North" in str(EvacState.objects.get(zone=north))
    # "restart": a fresh read from the database gives the same state; nothing returns to normal by itself
    with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(days=30)):
        assert services.effective_for(event, [str(north.pk)]).state is State.EVACUATE
    kinds = list(StateChange.objects.filter(event=event).order_by("at").values_list("kind", flat=True))
    assert kinds == ["raise", "raise"]
    assert AuditLog.objects.filter(action="evacuation.raise", event_id=event.pk).count() == 2


def test_never_back_to_normal_without_all_clear(event, admin):
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    with pytest.raises(Refused) as err:
        services.change(event, "normal", actor=admin, request=tf(admin))
    assert err.value.code == "needs_all_clear"
    services.change(event, "shelter_in_place", actor=admin, request=tf(admin))  # direct step down
    [clear] = services.change(event, "all_clear", actor=admin, request=tf(admin))
    assert clear.kind == "clear" and clear.from_state == "shelter_in_place"
    row = EvacState.objects.get(event=event, zone=None)
    assert row.clear_until - row.since == timedelta(minutes=5)
    [end] = services.change(event, "normal", actor=admin, request=tf(admin))
    assert end.kind == "end"
    assert StateChange.objects.filter(event=event, kind="step_down").exists()


def test_all_clear_time_from_settings(event, admin):
    settings_store.save("evacuation", "event", str(event.pk), {"all_clear_minutes": 1}, user=admin, event=event)
    services.change(event, "attention", actor=admin, request=tf(admin))
    services.change(event, "all_clear", actor=admin, request=tf(admin))
    later = timezone.now() + timedelta(seconds=61)
    with mock.patch("django.utils.timezone.now", return_value=later):
        assert services.effective_for(event, []).state is State.NORMAL


def test_disabled_states_and_labels(event, admin):
    settings_store.save("evacuation", "event", str(event.pk), {"staff_alert_enabled": False,
                                                               "evacuate_label": "Leave now"},
                        user=admin, event=event)
    cfg = services.config(event)
    assert State.STAFF_ALERT not in cfg.enabled and cfg.labels["evacuate"] == "Leave now"
    with pytest.raises(Refused):
        services.change(event, "staff_alert", actor=admin, request=tf(admin))


def test_event_all_clear_clears_zones_unless_unticked(event, admin, zones):
    north, south = zones["North"], zones["South"]
    services.change(event, "evacuate", zone=north, actor=admin, request=tf(admin))
    services.change(event, "attention", zone=south, actor=admin, request=tf(admin))
    services.change(event, "attention", actor=admin, request=tf(admin))
    done = services.change(event, "all_clear", actor=admin, request=tf(admin), clear_zones=[str(south.pk)])
    assert [d.zone_name for d in done] == ["", "South"]
    _ev, by_zone = services.statuses(event)
    assert by_zone[str(north.pk)].state is State.EVACUATE and by_zone[str(south.pk)].state is State.ALL_CLEAR
    # default: every zone in alarm
    services.change(event, "attention", actor=admin, request=tf(admin))
    done = services.change(event, "all_clear", actor=admin, request=tf(admin))
    assert {d.zone_name for d in done} == {"", "North"}


def test_real_alarm_ends_every_drill(event, admin, zones):
    north, south = zones["North"], zones["South"]
    services.change(event, "evacuate", drill=True, actor=admin, request=tf(admin))
    services.change(event, "attention", zone=north, drill=True, actor=admin, request=tf(admin))
    assert services.effective_for(event, [str(north.pk)]).drill
    audit_drill = AuditLog.objects.filter(action="evacuation.raise", drill=True).count()
    assert audit_drill == 2
    done = services.change(event, "staff_alert", zone=south, actor=admin, request=tf(admin))
    assert [d.kind for d in done][0] == "raise" and sorted(d.kind for d in done[1:]) == ["drill_ended"] * 2
    ev, by_zone = services.statuses(event)
    assert ev.state is State.NORMAL and by_zone[str(north.pk)].state is State.NORMAL
    shown = services.effective_for(event, [str(south.pk)])
    assert shown.state is State.STAFF_ALERT and not shown.drill
    # no drill may start while a real alarm is active anywhere in the event
    for zone in (None, north, south):
        with pytest.raises(Refused) as err:
            services.change(event, "evacuate", zone=zone, drill=True, actor=admin, request=tf(admin))
        assert err.value.code == "real_alarm_active"


def test_real_alarm_replaces_drill_in_same_scope(event, admin):
    services.change(event, "evacuate", drill=True, actor=admin, request=tf(admin))
    [real] = services.change(event, "attention", actor=admin, request=tf(admin))
    assert real.kind == "replace_drill" and not real.drill and real.from_drill
    [clear] = services.change(event, "all_clear", actor=admin, request=tf(admin))
    assert not clear.drill


def test_drill_all_clear_keeps_drill_flag(event, admin):
    services.change(event, "evacuate", drill=True, actor=admin, request=tf(admin))
    [clear] = services.change(event, "all_clear", actor=admin, request=tf(admin))
    assert clear.drill
    assert AuditLog.objects.filter(action="evacuation.clear", drill=True).exists()


def test_permissions(event, admin, role, zones, member):
    north, south = zones["North"], zones["South"]
    sec = person(event, role("security"), "sec@example.org")
    with pytest.raises(PermissionDenied):
        services.change(event, "attention", actor=member, request=tf(member))
    with pytest.raises(PermissionDenied):  # sensitive: needs a two-factor session
        services.change(event, "attention", actor=sec)
    services.change(event, "attention", actor=sec, request=tf(sec))
    with pytest.raises(PermissionDenied):  # security may raise but not clear, nor run drills
        services.change(event, "all_clear", actor=sec, request=tf(sec))
    services.change(event, "all_clear", actor=admin, request=tf(admin))
    with pytest.raises(PermissionDenied):
        services.change(event, "attention", zone=north, drill=True, actor=sec, request=tf(sec))
    # a control-room member limited to zone North
    cr = person(event, role("control-room"), "north@example.org", scope_kind="zone", scope_id=str(north.pk),
                scope_label="North")
    services.change(event, "evacuate", zone=north, actor=cr, request=tf(cr))
    for zone in (south, None):
        with pytest.raises(PermissionDenied):
            services.change(event, "evacuate", zone=zone, actor=cr, request=tf(cr))
    # event all clear by an admin, but the zone-scoped person cannot clear zones beyond theirs
    services.change(event, "attention", zone=south, actor=admin, request=tf(admin))
    services.change(event, "all_clear", zone=north, actor=cr, request=tf(cr))
    _ev, by_zone = services.statuses(event)
    assert by_zone[str(south.pk)].state is State.ATTENTION
    # system triggers (no actor) are checked by their callers (policies, roadmap 3.5)
    services.change(event, "evacuate", zone=south, source="test")


def test_event_all_clear_skips_zones_without_permission(event, admin, role, zones):
    north, south = zones["North"], zones["South"]
    orga = person(event, role("control-room"), "cr@example.org")
    services.change(event, "attention", actor=admin, request=tf(admin))
    services.change(event, "evacuate", zone=north, actor=admin, request=tf(admin))
    with mock.patch("apps.evacuation.services.can", side_effect=lambda u, e, t, drill, zone=None, request=None:
                    zone is None or zone.pk != north.pk):
        done = services.change(event, "all_clear", actor=orga, request=tf(orga))
    assert [d.zone_name for d in done] == [""]
    assert services.statuses(event)[1][str(north.pk)].state is State.EVACUATE
    assert south


def test_zone_must_belong_to_event(event, admin):
    other = Venue.objects.create(slug="else", name="Elsewhere", timezone="UTC")
    stray = Zone.objects.create(venue=other, name="Stray")
    with pytest.raises(Refused):
        services.change(event, "evacuate", zone=stray, actor=admin, request=tf(admin))


def test_webhook_emitted_after_commit(event, admin, django_capture_on_commit_callbacks):
    with mock.patch("apps.core.webhooks.emit") as emit:
        with django_capture_on_commit_callbacks(execute=True):
            services.change(event, "evacuate", drill=True, actor=admin, request=tf(admin))
    (kind, payload), kwargs = emit.call_args
    assert kind == "evacuation.state_changed" and kwargs["event"] == event
    assert payload["state"] == "evacuate" and payload["drill"] and payload["zone"] is None
    assert payload["kind"] == "raise" and payload["version"] == 1


def test_history_is_append_only(event, admin):
    [entry] = services.change(event, "attention", actor=admin, request=tf(admin))
    entry.reason = "edited"
    with pytest.raises(ValueError):
        entry.save()
    with pytest.raises(ValueError):
        entry.delete()
    assert "normal -> attention" in str(entry)


def test_refused_change_writes_nothing(event, admin):
    with pytest.raises(Refused):
        services.change(event, "all_clear", actor=admin, request=tf(admin))
    assert not StateChange.objects.exists() and not AuditLog.objects.filter(action__startswith="evacuation").exists()
    assert machine.current(EvacState(event=event).status, timezone.now()) == machine.NORMAL
