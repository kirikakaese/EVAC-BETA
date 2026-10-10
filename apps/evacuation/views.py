# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evacuation control page (ADR-0029). Triggers, policies and the PWA panic page follow in roadmap 3.5."""
from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.decorators.http import require_POST

from apps.core import settings_store
from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import acks, feed, machine, policy, services, triggers
from .forms import EVENT, ChangeForm, DrillForm, PolicyForm
from .guidance import Arrow
from .guidance import Kind as GuidanceKind
from .machine import Model, State
from .models import BlockedPoint, Bridge, EvacPolicy, EvacRequest, EvacState, ScheduledDrill, StaffAck, StateChange

MODULE = "evacuation"
MODEL_LABELS = [(Model.SIMPLE, _lazy("Simple takeover")), (Model.STAGED, _lazy("Staged, global")),
                (Model.ZONES, _lazy("Zones and routes"))]
GLYPHS = {Arrow.AHEAD: "↑", Arrow.AHEAD_RIGHT: "↗", Arrow.RIGHT: "→", Arrow.BACK_RIGHT: "↘", Arrow.BACK: "↓",
          Arrow.BACK_LEFT: "↙", Arrow.LEFT: "←", Arrow.AHEAD_LEFT: "↖"}
FORWARDED = _lazy("Sent to the venue node that holds this event. It runs there and shows up here once the node "
                  "reports back.")
#: brief §8.5: trigger to screen within 2 s (p95) on the venue LAN
TARGET_MS = 2000
ARROW_CHOICES = [("", _lazy("No arrow"))] + [(a.value, a.value.replace("_", " ")) for a in Arrow]


def _points(event: Any) -> list[dict[str, Any]]:
    """Exits, assembly points and passages that can be blocked (waypoints are not listed)."""
    blocked = {str(b.point_id): b for b in BlockedPoint.objects.filter(event=event).select_related("blocked_by")}
    return [{"point": p, "blocked": blocked.get(str(p.pk))}
            for p in services.points_of(event).exclude(kind="waypoint").order_by("venue__name", "kind", "name")]


def _screen_rows(event: Any, cfg: services.Config) -> list[dict[str, Any]]:
    from apps.venues.models import Point

    views = services.screen_views(event)
    seq = feed.current_seq(event)
    screen_acks = acks.screen_acks(event)
    ids = {v.guidance.toward for v in views} | {v.guidance.target for v in views}
    names = {str(p.pk): p.name for p in Point.objects.filter(pk__in=[i for i in ids if i])}
    rows = []
    for v in views:
        g = v.guidance
        state = v.shown.state.value
        rows.append({"screen": v.screen, "shown": {"state": state, "label": cfg.labels[state], "drill": v.shown.drill},
                     "kind": g.kind.value, "glyph": GLYPHS.get(g.arrow) if g.arrow else "",
                     "arrow": g.arrow.value.replace("_", " ") if g.arrow else "", "text": g.text,
                     "toward": names.get(g.toward or ""), "target": names.get(g.target or ""),
                     "distance": g.distance, "hint": services.hint_of(event, v.screen),
                     "follow_staff": g.kind is GuidanceKind.FOLLOW_STAFF,
                     "ack": screen_acks.get(str(v.screen.pk)), "seq": seq})
    return rows


def _rows(event: Any, labels: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    now = timezone.now()
    states = {str(r.zone_id) if r.zone_id else EVENT: r for r in EvacState.objects.filter(event=event)
              .select_related("changed_by")}
    ev_row = states.get(EVENT)
    ev = machine.current(ev_row.status, now) if ev_row else machine.NORMAL

    def info(status: machine.Status, row: EvacState | None) -> dict[str, Any]:
        return {"state": status.state.value, "label": labels[status.state.value], "drill": status.drill,
                "since": status.since, "clear_until": status.clear_until, "row": row,
                "alarm": status.alarm}

    zones = []
    for z in services.zones_of(event):
        row = states.get(str(z.pk))
        own = machine.current(row.status, now) if row else machine.NORMAL
        zones.append({"zone": z, "own": info(own, row), "shown": info(machine.effective([ev, own], now), None)})
    return info(ev, ev_row), zones


def _form(request: HttpRequest, event: Any, cfg: services.Config, zones: list[dict[str, Any]],
          data: Any = None) -> ChangeForm:
    alarm_zones = [z["zone"] for z in zones if z["own"]["alarm"]]
    can_drill = rbac.has_any(request.user, event, services.PERM_DRILL, request=request)
    # outside the zones model, zones are only offered to end an alarm they still have
    scopes = [z["zone"] for z in zones if cfg.model is Model.ZONES or z["own"]["state"] != "normal"]
    return ChangeForm(data, zones=scopes, labels=cfg.labels, enabled=cfg.enabled,
                      alarm_zones=alarm_zones, can_drill=can_drill)


def _forwarded(request: HttpRequest, event: Any) -> bool:
    from apps.nodes import guard

    if guard.remote(event):
        messages.info(request, FORWARDED)
        return True
    return False


def _can_change(request: HttpRequest, event: Any) -> bool:
    return any(rbac.has_any(request.user, event, p, request=request)
               for p in (services.PERM_TRIGGER, services.PERM_CLEAR, services.PERM_DRILL))


@event_view("evacuation.view", module=MODULE)
def index(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    return _page(request, event)


def _page(request: HttpRequest, event: Any, form: ChangeForm | None = None) -> HttpResponse:
    triggers.process_due(event)
    cfg = services.config(event)
    ev, zones = _rows(event, cfg.labels)
    can_change = _can_change(request, event)
    zones_model = cfg.model is Model.ZONES
    can_block = rbac.has_any(request.user, event, services.PERM_TRIGGER, request=request)
    return render(request, "evacuation/index.html", {
        "event": event, "ev": ev, "zones": zones if zones_model or any(z["own"]["alarm"] for z in zones) else [],
        "cfg": cfg, "can_change": can_change, "zones_model": zones_model,
        "model_label": dict(MODEL_LABELS)[cfg.model], "points": _points(event) if zones_model else [],
        "can_block": can_block, "screens": _screen_rows(event, cfg),
        "can_manage": rbac.has_any(request.user, event, "evacuation.manage", request=request),
        "arrow_choices": ARROW_CHOICES, "pending": triggers.pending(event),
        "form": form or (_form(request, event, cfg, zones) if can_change else None),
        "history": StateChange.objects.filter(event=event).select_related("actor")[:15],
        "labels": cfg.labels, **_propagation(event),
    }, status=400 if form is not None else 200)


def _propagation(event: Any) -> dict[str, Any]:
    cov = acks.coverage(event)
    since = acks.alarm_since(event)
    return {"cov": cov, "answers": acks.recent_staff(event, since) if since else [], "alarm_since": since,
            "target_ms": TARGET_MS, "slow": cov.last_p95_ms is not None and cov.last_p95_ms > TARGET_MS}


@event_view("evacuation.view", module=MODULE)
def propagation(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    """The "screens reached" card, refreshed by the control page every few seconds."""
    return render(request, "evacuation/_propagation.html", {"event": event, **_propagation(event)})


@require_POST
@event_view("evacuation.view", module=MODULE)
def answer(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    """A staff member answers the running alarm: "I'm on it", "zone clear", "need help"."""
    nxt = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        nxt = ""
    kind = request.POST.get("kind", "")
    zone_id = request.POST.get("zone", "")
    zone = next((z for z in services.zones_of(event) if str(z.pk) == zone_id), None)
    if kind not in dict(StaffAck.KINDS):
        messages.error(request, _("Unknown answer."))
    elif zone_id and zone is None:
        messages.error(request, _("Unknown zone."))
    elif acks.alarm_since(event) is None:
        messages.error(request, _("There is no alarm to answer."))
    else:
        acks.staff_ack(event, request.user, kind, zone=zone, note=request.POST.get("note", ""), request=request)
        messages.success(request, _("Sent to the control room: %(answer)s") % {"answer": dict(StaffAck.KINDS)[kind]})
    return redirect(nxt) if nxt else redirect("evacuation:index", event.slug)


@require_POST
@event_view("evacuation.view", module=MODULE)
def change(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    if not _can_change(request, event):
        raise PermissionDenied
    cfg = services.config(event)
    _ev, zones = _rows(event, cfg.labels)
    form = _form(request, event, cfg, zones, request.POST)
    if not form.is_valid():
        return _page(request, event, form)
    scope = form.cleaned_data["scope"]
    zone = None if scope == EVENT else next(z["zone"] for z in zones if str(z["zone"].pk) == scope)
    try:
        out = triggers.trigger(event, form.cleaned_data["state"], source=policy.WEB, zone=zone,
                               drill=bool(form.cleaned_data.get("drill")), actor=request.user, request=request,
                               reason=form.cleaned_data["reason"],
                               clear_zones=form.cleaned_data.get("clear_zones") if "clear_zones" in form.fields
                               else None)
    except machine.Refused as err:
        form.add_error(None, err.message)
        return _page(request, event, form)
    except PermissionDenied:
        form.add_error(None, _("You may not make this change here."))
        return _page(request, event, form)
    _report(request, out, cfg)
    return redirect("evacuation:index", event.slug)


def _report(request: HttpRequest, out: triggers.Outcome, cfg: services.Config) -> None:
    if out.result == "executed" and out.changes:
        first = out.changes[0]
        messages.success(request, _("%(where)s: %(state)s%(drill)s.") % {
            "where": first.zone_name or _("Whole event"), "state": cfg.labels[first.to_state],
            "drill": f" ({cfg.drill_text})" if first.drill and first.to_state != State.NORMAL else ""})
    elif out.result == "waiting" and out.request is not None:
        messages.warning(request, _("Waiting for a second person to confirm until %(t)s. Nothing has changed "
                                    "yet.") % {"t": timezone.localtime(out.request.deadline).strftime("%H:%M:%S")})
    elif out.result == "armed":
        messages.warning(request, _("Armed: the control room has to confirm this alarm."))
    elif out.result == "forwarded":
        messages.info(request, FORWARDED)
    else:
        messages.info(request, _("The control room was notified."))


@require_POST
@event_view("evacuation.view", module=MODULE)
def end_all_clear(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    zone_id = request.POST.get("zone") or None
    zone = None
    if zone_id:
        zone = services.zones_of(event).filter(pk=zone_id).first() if _uuid(zone_id) else None
        if zone is None:
            messages.error(request, _("Unknown zone."))
            return redirect("evacuation:index", event.slug)
    try:
        out = triggers.trigger(event, State.NORMAL, source=policy.WEB, zone=zone, actor=request.user,
                               request=request)
    except machine.Refused as err:
        messages.error(request, err.message)
    else:
        if out.result == "forwarded":
            messages.info(request, FORWARDED)
        else:
            messages.success(request, _("Back to normal."))
    return redirect("evacuation:index", event.slug)


def _uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


@event_view("evacuation.view", module=MODULE)
def history(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    cfg = services.config(event)
    rows = StateChange.objects.filter(event=event).select_related("actor")
    if request.GET.get("drills") == "only":
        rows = rows.filter(drill=True)
    elif request.GET.get("drills") == "none":
        rows = rows.filter(drill=False)
    return render(request, "evacuation/history.html", {"event": event, "history": rows[:500], "labels": cfg.labels,
                                                       "filter": request.GET.get("drills", "")})


@require_POST
@event_view("evacuation.view", module=MODULE)
def block(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    pid = request.POST.get("point", "")
    point = services.points_of(event).filter(pk=pid).first() if _uuid(pid) else None
    if point is None:
        messages.error(request, _("Unknown point."))
        return redirect("evacuation:index", event.slug)
    blocked = request.POST.get("blocked") == "1"
    try:
        services.set_blocked(event, point, blocked, actor=request.user, request=request,
                             reason=request.POST.get("reason", "")[:300])
    except PermissionDenied:
        messages.error(request, _("You may not block or open this point."))
    except machine.Refused as err:
        messages.error(request, err.message)
    else:
        if _forwarded(request, event):
            return redirect("evacuation:index", event.slug)
        messages.success(request, (_("%(p)s is blocked. Routes avoid it.") if blocked
                                   else _("%(p)s is open again.")) % {"p": point.name})
    return redirect("evacuation:index", event.slug)


@require_POST
@event_view("evacuation.manage", module=MODULE)
def hint(request: HttpRequest, slug: str, pk: str, *, event: Any) -> HttpResponse:
    screen = next((s for s in services._screens(event) if str(s.pk) == str(pk)), None)
    if screen is None:
        messages.error(request, _("Unknown screen."))
        return redirect("evacuation:index", event.slug)
    arrow = request.POST.get("hint_arrow", "")
    if arrow not in dict(ARROW_CHOICES):
        arrow = ""
    from apps.core import settings_store

    settings_store.save("evacuation_screen", "screen", str(screen.pk),
                        {"hint_text": request.POST.get("hint_text", "")[:80].strip(), "hint_arrow": arrow},
                        user=request.user, event=event)
    messages.success(request, _("Direction for %(s)s saved.") % {"s": screen.name})
    return redirect("evacuation:index", event.slug)


def _request_of(event: Any, pk: Any) -> EvacRequest | None:
    req: EvacRequest | None = EvacRequest.objects.filter(event=event, pk=pk).select_related("zone").first()
    return req


@require_POST
@event_view("evacuation.view", module=MODULE)
def decide(request: HttpRequest, slug: str, pk: Any, verdict: str, *, event: Any) -> HttpResponse:
    req = _request_of(event, pk)
    if req is None:
        messages.error(request, _("Unknown request."))
        return redirect("evacuation:index", event.slug)
    try:
        if verdict == "confirm":
            triggers.confirm(req, actor=request.user, request=request)
            if not _forwarded(request, event):
                messages.success(request, _("Confirmed."))
        else:
            triggers.reject(req, actor=request.user, request=request)
            if not _forwarded(request, event):
                messages.success(request, _("Rejected. Nothing changed."))
    except machine.Refused as err:
        messages.error(request, err.message)
    except PermissionDenied:
        messages.error(request, _("You may not decide this request."))
    back = "evacuation:panic" if request.POST.get("next") == "panic" else "evacuation:index"
    return redirect(back, event.slug)


@event_view("evacuation.view", module=MODULE)
def panic(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    """The mobile panic page (staff app): big hold-to-confirm buttons per stage, zone choice."""
    cfg = services.config(event)
    triggers.process_due(event)
    can_raise = rbac.has_any(request.user, event, services.PERM_TRIGGER, request=request)
    can_drill = rbac.has_any(request.user, event, services.PERM_DRILL, request=request)
    zones = list(services.zones_of(event)) if cfg.model is Model.ZONES else []
    if request.method == "POST":
        if not (can_raise or can_drill):
            raise PermissionDenied
        state = request.POST.get("state", "")
        zone_id = request.POST.get("zone", "")
        zone = next((z for z in zones if str(z.pk) == zone_id), None)
        try:
            out = triggers.trigger(event, state, source=policy.PANIC, zone=zone, actor=request.user,
                                   request=request, drill=request.POST.get("drill") == "on",
                                   reason=request.POST.get("reason", "")[:300])
        except ValueError:
            messages.error(request, _("Unknown state."))
        except machine.Refused as err:
            messages.error(request, err.message)
        except PermissionDenied:
            messages.error(request, _("You may not raise this alarm here."))
        else:
            _report(request, out, cfg)
        return redirect("evacuation:panic", event.slug)
    ev, _zones = _rows(event, cfg.labels)
    stages = sorted((s for s in cfg.enabled if s in machine.ALARMS), key=lambda s: -machine.SEVERITY[s])
    return render(request, "evacuation/panic.html", {
        "event": event, "ev": ev, "cfg": cfg, "zones": zones, "can_raise": can_raise, "can_drill": can_drill,
        "stages": [(s.value, cfg.labels[s.value]) for s in stages], "pending": triggers.pending(event),
        "alarm": acks.alarm_since(event) is not None})


@event_view("evacuation.manage", module=MODULE)
def policies(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    cfg = services.config(event)
    zones = list(services.zones_of(event))
    srcs = triggers.sources()
    pform = PolicyForm(sources=srcs, zones=zones, labels=cfg.labels, prefix="policy")
    dform = DrillForm(zones=zones, labels=cfg.labels, enabled=cfg.enabled, prefix="drill")
    if request.method == "POST":
        what = request.POST.get("what")
        if what == "policy":
            pform = PolicyForm(request.POST, sources=srcs, zones=zones, labels=cfg.labels, prefix="policy")
            if pform.is_valid():
                d = pform.cleaned_data
                zone = next((z for z in zones if str(z.pk) == d["zone"]), None)
                triggers.save_policy(event, source=d["source"], state=d["state"], zone=zone, action=d["action"],
                                     escalate_seconds=d["escalate_seconds"], actor=request.user, request=request)
                messages.success(request, _("Policy saved."))
                return redirect("evacuation:policies", event.slug)
        elif what == "drill":
            dform = DrillForm(request.POST, zones=zones, labels=cfg.labels, enabled=cfg.enabled, prefix="drill")
            if dform.is_valid():
                d = dform.cleaned_data
                zone = next((z for z in zones if str(z.pk) == d["zone"]), None)
                triggers.schedule_drill(event, at=d["at"], state=d["state"], zone=zone, note=d["note"],
                                        actor=request.user, request=request)
                messages.success(request, _("Drill scheduled."))
                return redirect("evacuation:policies", event.slug)
        elif what in ("delete_policy", "delete_drill"):
            pk = request.POST.get("pk", "")
            if _uuid(pk):
                if what == "delete_policy":
                    triggers.delete_policy(event, pk, actor=request.user, request=request)
                else:
                    triggers.delete_drill(event, pk, actor=request.user, request=request)
            messages.success(request, _("Deleted."))
            return redirect("evacuation:policies", event.slug)
    names = dict(srcs)
    rows = []
    for p in EvacPolicy.objects.filter(event=event).select_related("zone"):
        rows.append({"p": p, "source": names.get(p.source, p.source), "state": cfg.labels.get(p.state, "")})
    defaults = [(names[k], dict(EvacPolicy.ACTIONS)[policy.DEFAULTS.get(k, policy.Action.ARM).value])
                for k, _n in srcs]
    two, seconds = triggers.two_person(event)
    return render(request, "evacuation/policies.html", {
        "event": event, "rows": rows, "defaults": defaults, "pform": pform, "dform": dform,
        "drills": ScheduledDrill.objects.filter(event=event).select_related("zone"),
        "two_person": [cfg.labels.get(s, s) for s in sorted(two)], "two_seconds": seconds,
        "escalate_default": policy.DEFAULT_ESCALATE}, status=400 if request.method == "POST" else 200)


@event_view("evacuation.manage", module=MODULE)
def bridges_page(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    from . import bridges

    zones = {str(z.pk): z.name for z in services.zones_of(event)}
    new_token = ""
    errors: dict[str, str] = {}
    if request.method == "POST":
        what = request.POST.get("what")
        pk = request.POST.get("pk", "")
        bridge = Bridge.objects.filter(event=event, pk=pk).first() if _uuid(pk) else None
        if what == "add":
            name = request.POST.get("name", "").strip()
            if not name:
                errors["add"] = _("Give the bridge a name.")
            else:
                bridge, new_token = bridges.create(event, name, actor=request.user, request=request)
        elif bridge is None:
            messages.error(request, _("Unknown bridge."))
            return redirect("evacuation:bridges", event.slug)
        elif what == "inputs":
            try:
                parsed = bridges.parse_inputs(request.POST.get("inputs", ""), zones)
            except ValueError as err:
                errors[str(bridge.pk)] = str(err)
            else:
                bridges.set_inputs(bridge, parsed, actor=request.user, request=request)
                messages.success(request, _("Inputs saved."))
                return redirect("evacuation:bridges", event.slug)
        elif what == "rotate":
            new_token = bridges.rotate(bridge, actor=request.user, request=request)
        elif what == "delete":
            bridges.delete(bridge, actor=request.user, request=request)
            messages.success(request, _("Bridge removed."))
            return redirect("evacuation:bridges", event.slug)
    rows = [{"b": b, "inputs_text": bridges.format_inputs(b, zones),
             "states": [(i, (b.status.get("inputs") or {}).get(i["key"], "unknown")) for i in b.inputs],
             "error": errors.get(str(b.pk), "")} for b in Bridge.objects.filter(event=event)]
    return render(request, "evacuation/bridges.html", {
        "event": event, "rows": rows, "new_token": new_token, "add_error": errors.get("add", ""),
        "base_url": request.build_absolute_uri("/bridge/v1/"), "offline_after": bridges.OFFLINE_AFTER,
        "heartbeat": bridges.HEARTBEAT_SECONDS}, status=400 if errors else 200)


@event_view("evacuation.view", module=MODULE)
def readiness_page(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    """Fail-safe readiness (roadmap 3.9): per screen bundle, sound, self-test; the alarm key; bridges."""
    from apps.accounts import twofactor

    from . import alarmkey, readiness

    can_manage = rbac.has_any(request.user, event, "evacuation.manage", request=request)
    exported = ""
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied
        what = request.POST.get("what")
        if what == "selftest":
            visible = request.POST.get("visible") == "on"
            if visible and acks.alarm_since(event) is not None:
                messages.error(request, _("No visible self-test during an alarm."))
            else:
                n = readiness.run_selftest(event, visible=visible, seconds=_int(request.POST.get("seconds"), 5),
                                           actor=request.user, request=request)
                messages.success(request, _("Self-test sent to %(n)s screens. Results appear here within a minute.")
                                 % {"n": n})
            return redirect("evacuation:readiness", event.slug)
        if what in ("rotate", "export"):
            if not twofactor.is_verified(request):
                messages.error(request, _("The alarm key needs a session confirmed with two factors."))
                return redirect("evacuation:readiness", event.slug)
            if what == "rotate":
                alarmkey.rotate(event, actor=request.user, request=request)
                feed.push(event)
                messages.success(request, _("New alarm key. Screens get it with their next bundle; the old key stays "
                                            "valid for 24 hours. Give bridges and secondary nodes the new key."))
                return redirect("evacuation:readiness", event.slug)
            exported = alarmkey.export_private(event, actor=request.user, request=request,
                                               purpose=request.POST.get("purpose", "")[:100])
    rows = readiness.screens(event)
    key = alarmkey.ensure(event)
    return render(request, "evacuation/readiness.html", {
        "event": event, "rows": rows, "summary": readiness.summary(rows), "can_manage": can_manage,
        "key": key, "previous_valid": key.previous_public_key and key.previous_valid_until
        and key.previous_valid_until > timezone.now(), "exported": exported,
        "bridges": Bridge.objects.filter(event=event),
        "origins": settings_store.get("evacuation", event=event).get("fallback_origins") or [],
        "selftest_days": readiness.SELFTEST_MAX_AGE.days})


@event_view("evacuation.manage", module=MODULE)
def content_page(request: HttpRequest, slug: str, *, event: Any) -> HttpResponse:
    from . import content
    from .models import SOUNDS, StageContent

    cfg = services.config(event)
    layouts = content.layouts_of(event)
    by_id = {str(lay.pk): lay for lay in layouts}
    errors: dict[str, str] = {}
    if request.method == "POST":
        state = request.POST.get("state", "")
        if state in {s.value for s in content.STAGES}:
            lay = by_id.get(request.POST.get("layout", ""))
            try:
                content.save(event, state, layout=lay, texts=request.POST.get("texts", "").splitlines(),
                             rotate_seconds=_int(request.POST.get("rotate_seconds"), 8),
                             pictograms_only=request.POST.get("pictograms_only") == "on",
                             sound=request.POST.get("sound") if request.POST.get("sound") in dict(SOUNDS) else "none",
                             sound_every=_int(request.POST.get("sound_every"), 30),
                             speech_text=request.POST.get("speech_text", ""), actor=request.user, request=request)
            except ValueError as err:
                errors[state] = str(err)
            else:
                messages.success(request, _("Saved. Screens show it the next time this stage is active."))
                return redirect("evacuation:content", event.slug)
    rows = []
    for stage in content.STAGES:
        row = StageContent.objects.filter(event=event, state=stage.value).first()
        lay = by_id.get(str(row.layout_id)) if row and row.layout_id else None
        found = []
        if lay is not None:
            data = lay.published.data if lay.published_id else lay.data
            found = content.findings(event, lay, data)
        effective = feed.stage_content(event, stage.value)
        rows.append({"state": stage.value, "label": cfg.labels.get(stage.value, stage.value), "row": row,
                     "enabled": stage in cfg.enabled, "layout": lay, "findings": found,
                     "texts": "\n".join(row.texts if row and row.texts else effective["texts"]),
                     "default_texts": not (row and row.texts), "sound": effective["sound"],
                     "error": errors.get(stage.value, "")})
    return render(request, "evacuation/content.html", {
        "event": event, "rows": rows, "layouts": layouts, "sounds": SOUNDS, "tts": content.tts_available(),
        "zones_model": cfg.model is Model.ZONES}, status=400 if errors else 200)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
