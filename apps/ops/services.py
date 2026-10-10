# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operations services (ADR-0039): every change to incidents, the ops log, tasks and escalation rules goes through
here, writes the audit log and the incident timeline, and tells integrations (webhooks ``incident.*``) and the
control room (realtime) about it.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import modules, settings_store, webhooks
from apps.core.audit import log

from .models import SEVERITY_RANK, Escalation, EscalationRule, Incident, IncidentUpdate, LogEntry, Task

MODULE = "ops"
DEFAULT_CATEGORIES = ["Security", "Medical", "Fire", "Technical", "Crowd", "Lost child", "Lost property", "Weather",
                      "Other"]
MAX_ATTACHMENT = 10 * 1024 * 1024
ATTACHMENT_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".txt", ".mp3", ".m4a", ".ogg", ".wav")


def ops_settings(event: Any) -> dict[str, Any]:
    return settings_store.get("ops", event=event)


def categories(event: Any) -> list[str]:
    cats = [c.strip() for c in (ops_settings(event).get("categories") or []) if str(c).strip()]
    return cats or DEFAULT_CATEGORIES


def _user(actor: Any) -> Any:
    return actor if getattr(actor, "pk", None) and getattr(actor, "is_authenticated", True) else None


def _place(inc: Incident) -> str:
    parts = [inc.room.name if inc.room_id else "", inc.zone.name if inc.zone_id and not inc.room_id else "",
             inc.location]
    return ", ".join(p for p in parts if p)


def incident_url(inc: Incident) -> str:
    return reverse("ops:incident", args=[inc.event.slug, inc.pk])


def payload_of(inc: Incident) -> dict[str, Any]:
    return {"id": str(inc.pk), "event": inc.event.slug, "number": inc.number, "title": inc.title,
            "category": inc.category, "severity": inc.severity, "status": inc.status,
            "zone": str(inc.zone_id) if inc.zone_id else None, "room": str(inc.room_id) if inc.room_id else None,
            "place": _place(inc), "assignee": str(inc.assignee) if inc.assignee_id else None, "team": inc.team,
            "created_at": inc.created_at.isoformat() if inc.created_at else None}


def _after_commit(event: Any, kind: str, inc: Incident) -> None:
    def run() -> None:
        webhooks.emit(kind, payload_of(inc), event=event)
    transaction.on_commit(run)


def _timeline(inc: Incident, kind: str, text: str, *, actor: Any = None, data: dict[str, Any] | None = None,
              attachment: Any = None) -> IncidentUpdate:
    u = IncidentUpdate(incident=inc, kind=kind, text=text, data=data or {}, actor=_user(actor))
    if attachment is not None:
        u.attachment_name = getattr(attachment, "name", "file")[:200]
        u.attachment.save(u.attachment_name, attachment, save=False)
    u.save()
    return u


# ------------------------------------------------------------------ incidents
def _validate(inc: Incident) -> None:
    if not inc.title.strip():
        raise ValidationError(_("A title is needed."))
    if inc.severity not in SEVERITY_RANK:
        raise ValidationError(_("Unknown severity."))
    if inc.zone_id and not inc.event.venues.filter(pk=inc.zone.venue_id).exists():
        raise ValidationError(_("The zone belongs to another venue."))
    if inc.room_id and not inc.event.venues.filter(pk=inc.room.venue_id).exists():
        raise ValidationError(_("The room belongs to another venue."))


def create_incident(inc: Incident, *, actor: Any, request: Any = None, note: str = "") -> Incident:
    """Report an incident: it gets the next number of the event, a timeline, an ops log line and escalation."""
    _validate(inc)
    inc.created_by = inc.created_by or _user(actor)
    for _attempt in range(5):
        try:
            with transaction.atomic():
                inc.number = (Incident.objects.filter(event=inc.event).aggregate(n=Max("number"))["n"] or 0) + 1
                inc.save()
                break
        except IntegrityError:  # two reports at the same moment: take the next number
            inc._state.adding = True
            continue
    else:
        raise ValidationError(_("Could not number the incident; try again."))
    _timeline(inc, IncidentUpdate.Kind.CREATED, note or inc.description, actor=actor,
              data={"severity": inc.severity, "category": inc.category})
    system_log(inc.event, _("Incident #%(n)s opened: %(t)s (%(s)s%(p)s)") % {
        "n": inc.number, "t": inc.title, "s": inc.get_severity_display(),
        "p": f", {_place(inc)}" if _place(inc) else ""}, source="incident.created", incident=inc,
        important=inc.rank >= SEVERITY_RANK["high"])
    log(action="ops.incident_created", actor=actor, target=inc, event=inc.event, request=request,
        message=f"Incident #{inc.number} {inc.title}", changes=payload_of(inc))
    _after_commit(inc.event, "incident.created", inc)
    if inc.assignee_id:
        _tell_assignee(inc, actor)
    transaction.on_commit(lambda: escalate(inc.pk))
    return inc


EDITABLE = ("title", "description", "category", "severity", "zone", "room", "location", "assignee", "team",
            "reported_by")


def update_incident(inc: Incident, changed: list[str], *, actor: Any, request: Any = None,
                    before: dict[str, Any] | None = None) -> Incident:
    """Save an edit (the form already set the fields); ``before`` holds the old values for the timeline."""
    _validate(inc)
    changed = [f for f in changed if f in EDITABLE]
    if not changed:
        return inc
    inc.version += 1
    inc.save()
    before = before or {}
    if "severity" in changed:
        _timeline(inc, IncidentUpdate.Kind.SEVERITY, _("Severity: %(s)s") % {"s": inc.get_severity_display()},
                  actor=actor, data={"from": before.get("severity"), "to": inc.severity})
    if "assignee" in changed or "team" in changed:
        who = ", ".join(x for x in [str(inc.assignee) if inc.assignee_id else "", inc.team] if x) or _("nobody")
        _timeline(inc, IncidentUpdate.Kind.ASSIGNED, _("Assigned to %(w)s") % {"w": who}, actor=actor)
        if "assignee" in changed and inc.assignee_id:
            _tell_assignee(inc, actor)
    rest = [f for f in changed if f not in ("severity", "assignee", "team")]
    if rest:
        _timeline(inc, IncidentUpdate.Kind.EDITED, _("Changed: %(f)s") % {
            "f": ", ".join(str(Incident._meta.get_field(f).verbose_name) for f in rest)}, actor=actor,
            data={"fields": rest})
    log(action="ops.incident_edited", actor=actor, target=inc, event=inc.event, request=request,
        message=f"Incident #{inc.number} {inc.title}", changes={"changed": changed})
    _after_commit(inc.event, "incident.updated", inc)
    if "severity" in changed:
        transaction.on_commit(lambda: escalate(inc.pk))  # a higher severity may match more rules
    return inc


def _tell_assignee(inc: Incident, actor: Any) -> None:
    from apps.core.notify import notify

    if inc.assignee_id and inc.assignee_id != getattr(actor, "pk", None):
        notify([inc.assignee], _("Incident #%(n)s assigned to you: %(t)s") % {"n": inc.number, "t": inc.title},
               body=_place(inc), url=incident_url(inc), level="warn" if inc.rank >= 3 else "info", event=inc.event)


TRANSITIONS = {
    Incident.Status.NEW: {Incident.Status.ACKNOWLEDGED, Incident.Status.IN_PROGRESS, Incident.Status.RESOLVED,
                          Incident.Status.CLOSED},
    Incident.Status.ACKNOWLEDGED: {Incident.Status.IN_PROGRESS, Incident.Status.RESOLVED, Incident.Status.CLOSED},
    Incident.Status.IN_PROGRESS: {Incident.Status.RESOLVED, Incident.Status.CLOSED, Incident.Status.ACKNOWLEDGED},
    Incident.Status.RESOLVED: {Incident.Status.CLOSED, Incident.Status.IN_PROGRESS},
    Incident.Status.CLOSED: {Incident.Status.IN_PROGRESS},
}


def set_status(inc: Incident, status: str, *, actor: Any, request: Any = None, note: str = "") -> Incident:
    if status not in Incident.Status.values:
        raise ValidationError(_("Unknown status."))
    if status not in TRANSITIONS.get(inc.status, set()):
        raise ValidationError(_("An incident that is %(a)s cannot become %(b)s.") % {
            "a": inc.get_status_display().lower(), "b": Incident.Status(status).label.lower()})
    now = timezone.now()
    before = inc.status
    inc.status = status
    if status != Incident.Status.NEW and inc.acknowledged_at is None:
        inc.acknowledged_at = now
    if status == Incident.Status.RESOLVED:
        inc.resolved_at = now
    if status == Incident.Status.CLOSED:
        inc.closed_at = now
        inc.resolved_at = inc.resolved_at or now
    if status == Incident.Status.IN_PROGRESS and before in (Incident.Status.RESOLVED, Incident.Status.CLOSED):
        inc.resolved_at = inc.closed_at = None  # reopened
    inc.version += 1
    inc.save()
    label = inc.get_status_display()
    _timeline(inc, IncidentUpdate.Kind.STATUS, label + (f": {note}" if note else ""), actor=actor,
              data={"from": before, "to": status})
    if status in (Incident.Status.RESOLVED, Incident.Status.CLOSED) or before in (Incident.Status.RESOLVED,
                                                                                  Incident.Status.CLOSED):
        system_log(inc.event, _("Incident #%(n)s %(s)s: %(t)s") % {"n": inc.number, "s": label.lower(),
                                                                    "t": inc.title} + (f" ({note})" if note else ""),
                   source="incident.updated", incident=inc)
    log(action=f"ops.incident_{status}", actor=actor, target=inc, event=inc.event, request=request,
        message=f"Incident #{inc.number} {inc.title}: {label}", changes={"status": [before, status]})
    _after_commit(inc.event, "incident.updated", inc)
    return inc


def add_note(inc: Incident, text: str, *, actor: Any, request: Any = None, attachment: Any = None) -> IncidentUpdate:
    text = (text or "").strip()
    if not text and attachment is None:
        raise ValidationError(_("Write a note or attach a file."))
    if attachment is not None:
        name = getattr(attachment, "name", "").lower()
        if not name.endswith(ATTACHMENT_TYPES):
            raise ValidationError(_("Attach a photo, PDF, text or audio file."))
        if getattr(attachment, "size", 0) > MAX_ATTACHMENT:
            raise ValidationError(_("The file is larger than 10 MB."))
    u = _timeline(inc, IncidentUpdate.Kind.ATTACHMENT if attachment is not None else IncidentUpdate.Kind.NOTE,
                  text, actor=actor, attachment=attachment)
    Incident.objects.filter(pk=inc.pk).update(updated_at=timezone.now())
    log(action="ops.incident_note", actor=actor, target=inc, event=inc.event, request=request,
        message=f"Incident #{inc.number}: note" + (" with attachment" if attachment is not None else ""))
    return u


def link(inc: Incident, *, kind: str, ident: str, label: str, url: str = "", actor: Any = None,
         request: Any = None) -> Incident:
    """Link something of another module (an announcement, an alarm) to the incident."""
    entry = {"kind": kind[:40], "id": str(ident)[:100], "label": label[:200], "url": url[:300]}
    if any(x.get("kind") == entry["kind"] and x.get("id") == entry["id"] for x in inc.links):
        return inc
    inc.links = [*inc.links, entry]
    inc.save(update_fields=["links", "updated_at"])
    _timeline(inc, IncidentUpdate.Kind.LINK, label, actor=actor, data=entry)
    log(action="ops.incident_linked", actor=actor, target=inc, event=inc.event, request=request,
        message=f"Incident #{inc.number} linked to {kind} {label}")
    return inc


# ------------------------------------------------------------------ ops log
def add_entry(event: Any, text: str, *, actor: Any, sender: str = "", recipient: str = "", important: bool = False,
              incident: Incident | None = None, client_id: str = "", at: dt.datetime | None = None,
              request: Any = None) -> LogEntry:
    """A person's ops log entry. ``client_id`` makes a replay from the staff app's offline queue harmless."""
    text = (text or "").strip()
    if not text:
        raise ValidationError(_("The message is empty."))
    if incident is not None and incident.event_id != event.pk:
        raise ValidationError(_("The incident belongs to another event."))
    client_id = (client_id or "")[:64]
    if client_id:
        old = LogEntry.objects.filter(event=event, client_id=client_id).first()
        if old is not None:
            return old
    now = timezone.now()
    # an entry written offline keeps the time it was written (never in the future, at most a day back)
    when = min(at, now) if at is not None and at > now - dt.timedelta(days=1) else now
    e = LogEntry.objects.create(event=event, at=when, kind=LogEntry.Kind.MESSAGE, sender=sender[:80],
                                recipient=recipient[:80], text=text[:4000], important=important, incident=incident,
                                author=_user(actor), client_id=client_id)
    log(action="ops.log_entry", actor=actor, target=e, event=event, request=request,
        message=(f"{sender} → {recipient}: " if sender or recipient else "") + text[:200])
    _push(event, e)
    return e


def system_log(event: Any, text: str, *, source: str, important: bool = False,
               incident: Incident | None = None) -> LogEntry | None:
    """An entry the system writes (alarms, screens, DECT, occupancy, incidents)."""
    if not modules.is_enabled(MODULE, event):
        return None
    e = LogEntry.objects.create(event=event, at=timezone.now(), kind=LogEntry.Kind.SYSTEM, text=text[:4000],
                                source=source[:80], important=important, incident=incident)
    _push(event, e)
    return e


def _push(event: Any, e: LogEntry) -> None:
    from apps.core import realtime

    data = {"id": str(e.pk), "at": e.at.isoformat(), "kind": e.kind, "sender": e.sender, "recipient": e.recipient,
            "text": e.text, "important": e.important}
    transaction.on_commit(lambda: realtime.publish(event, "ops.log", data))


def _evac_text(p: dict[str, Any]) -> tuple[str, bool]:
    where = p.get("zone_name") or _("the whole event")
    drill = _(" (drill)") if p.get("drill") else ""
    return _("Evacuation state of %(w)s: %(s)s%(d)s") % {"w": where, "s": p.get("state", "?"), "d": drill}, \
        p.get("state") not in ("normal", None)


def sink(event_type: str, payload: Any, event: Any) -> None:
    """Webhook sink: what other modules report becomes a system line in the ops log (ADR-0039)."""
    if event is None or not modules.is_enabled(MODULE, event) or not ops_settings(event).get("log_system_events",
                                                                                             True):
        return
    p = dict(payload or {})
    text, important = "", False
    if event_type == "evacuation.state_changed":
        text, important = _evac_text(p)
    elif event_type == "evacuation.staff_ack":
        text = _("Staff answer to the alarm: %(k)s by %(u)s") % {"k": p.get("kind", "?"), "u": p.get("user", "?")}
        if p.get("note"):
            text += f" ({p['note']})"
    elif event_type == "evacuation.routes_changed":
        text = _("Routes changed (exit or passage blocked or opened)")
    elif event_type == "screen.offline":
        text, important = _("Screen offline: %(n)s") % {"n": p.get("name", "?")}, False
    elif event_type == "screen.online":
        text = _("Screen back online: %(n)s") % {"n": p.get("name", "?")}
    elif event_type == "dial.dect_alert":
        text = _("DECT: %(m)s") % {"m": p.get("message") or p.get("kind", "?")}
        important = p.get("severity") in ("error", "critical", "high")
    elif event_type == "announcement.published":
        text = _("Announcement sent: %(t)s") % {"t": p.get("title", "?")}
    elif event_type == "announcement.cancelled":
        text = _("Announcement cancelled: %(t)s") % {"t": p.get("title", "?")}
    elif event_type == "override.started":
        text = _("Screen override started: %(t)s") % {"t": p.get("title") or p.get("name") or "?"}
    elif event_type == "override.cancelled":
        text = _("Screen override ended: %(t)s") % {"t": p.get("title") or p.get("name") or "?"}
    elif event_type == "occupancy.state_changed":
        text = _("Occupancy %(a)s: %(s)s (%(v)s / %(c)s)") % {"a": p.get("name", "?"), "s": p.get("state", "?"),
                                                                 "v": p.get("value", "?"), "c": p.get("capacity", "?")}
        important = p.get("state") == "full"
    elif event_type == "program.session_changed" and (p.get("status") == "cancelled" or p.get("moved")):
        text = _("Program: %(t)s %(w)s") % {"t": p.get("title", "?"), "w": _("cancelled") if p.get(
            "status") == "cancelled" else _("moved to %(s)s") % {"s": p.get("stage") or "?"}}
    elif event_type == "crew.no_show":
        text = _("No-show: %(m)s on %(t)s (%(n)s missing)") % {"m": p.get("member", "?"), "t": p.get("title", "?"),
                                                              "n": p.get("missing", "?")}
    elif event_type == "inventory.overdue":
        text = _("Not returned: %(i)s %(n)s (%(b)s)") % {"i": p.get("item", "?"), "n": p.get("name", ""),
                                                        "b": p.get("borrower", "?")}
    elif event_type == "helpdesk.request" and p.get("category") == "accessibility":
        text = _("Accessibility request: %(s)s") % {"s": p.get("subject", "?")}
    if text:
        system_log(event, text, source=event_type, important=important)


# ------------------------------------------------------------------ tasks
def save_task(t: Task, *, actor: Any, request: Any = None) -> Task:
    if not t.title.strip():
        raise ValidationError(_("A task needs a title."))
    created = t._state.adding
    t.created_by = t.created_by or _user(actor)
    t.save()
    if created and t.incident_id:
        _timeline(t.incident, IncidentUpdate.Kind.NOTE, _("Task: %(t)s") % {"t": t.title}, actor=actor)
    if created and t.assignee_id and t.assignee_id != getattr(actor, "pk", None):
        from apps.core.notify import notify

        notify([t.assignee], _("Task for you: %(t)s") % {"t": t.title}, body=t.notes[:300],
               url=reverse("ops:tasks", args=[t.event.slug]), event=t.event)
    log(action="ops.task_created" if created else "ops.task_edited", actor=actor, target=t, event=t.event,
        request=request, message=t.title)
    return t


def set_task_done(t: Task, done: bool, *, actor: Any, request: Any = None) -> Task:
    t.status = Task.Status.DONE if done else Task.Status.OPEN
    t.done_at = timezone.now() if done else None
    t.done_by = _user(actor) if done else None
    t.save(update_fields=["status", "done_at", "done_by"])
    if t.incident_id:
        _timeline(t.incident, IncidentUpdate.Kind.NOTE, (_("Task done: %(t)s") if done else _("Task reopened: %(t)s"))
                  % {"t": t.title}, actor=actor)
    log(action="ops.task_done" if done else "ops.task_reopened", actor=actor, target=t, event=t.event,
        request=request, message=t.title)
    return t


# ------------------------------------------------------------------ escalation
def rule_matches(rule: EscalationRule, inc: Incident) -> bool:
    if not rule.enabled or SEVERITY_RANK.get(inc.severity, 0) < SEVERITY_RANK.get(rule.min_severity, 9):
        return False
    if rule.categories and inc.category not in rule.categories:
        return False
    if rule.until == "unacknowledged":
        return inc.status == Incident.Status.NEW
    return inc.status in Incident.OPEN


def escalate(incident_id: Any, now: dt.datetime | None = None) -> int:
    """Fire the rules that are due for one incident (each rule once). Returns how many fired."""
    inc = Incident.objects.select_related("event", "zone", "room").filter(pk=incident_id).first()
    if inc is None or not modules.is_enabled(MODULE, inc.event):
        return 0
    now = now or timezone.now()
    fired = 0
    done = set(inc.escalations.values_list("rule_id", flat=True))
    for rule in EscalationRule.objects.filter(event=inc.event, enabled=True).prefetch_related("roles"):
        if rule.pk in done or not rule_matches(rule, inc):
            continue
        if inc.created_at + dt.timedelta(minutes=rule.after_minutes) > now:
            continue
        if _fire(rule, inc):
            fired += 1
    return fired


def _recipients(rule: EscalationRule, inc: Incident) -> list[Any]:
    from apps.events import rbac
    from apps.events.models import RoleAssignment

    role_ids = [r.pk for r in rule.roles.all()]
    if not role_ids:
        return []
    users = {a.membership.user for a in RoleAssignment.objects.filter(role_id__in=role_ids, role__event=inc.event)
             .select_related("membership__user") if a.membership.user.is_active}
    return [u for u in users if "ops.view" in rbac.effective(u, inc.event, two_factor=True).permissions]


def _fire(rule: EscalationRule, inc: Incident) -> bool:
    from apps.core import alerts
    from apps.core.notify import notify
    from apps.core.plugins import Alert

    try:
        with transaction.atomic():
            esc = Escalation.objects.create(incident=inc, rule=rule, rule_name=rule.name)
    except IntegrityError:
        return False  # fired concurrently
    title = _("Incident #%(n)s (%(s)s): %(t)s") % {"n": inc.number, "s": inc.get_severity_display(), "t": inc.title}
    waited = int((timezone.now() - inc.created_at).total_seconds() // 60)
    body = ", ".join(x for x in [inc.category, _place(inc),
                                 _("open for %(m)s min, not acknowledged") % {"m": waited}
                                 if rule.after_minutes and inc.status == Incident.Status.NEW else ""] if x)
    level = "err" if inc.rank >= SEVERITY_RANK["critical"] else ("warn" if inc.rank >= SEVERITY_RANK["high"]
                                                                  else "info")
    users = _recipients(rule, inc)
    n = notify(users, title, body=body, url=incident_url(inc), level=level, event=inc.event)
    usable = alerts.channels(inc.event)
    keys = [c for c in rule.channels or [] if c in usable]
    sent = alerts.enqueue(inc.event, keys, Alert(title=title, body=body, level=level, url=incident_url(inc),
                                                 key=f"incident:{inc.pk}:{rule.pk}"))
    esc.recipients = n
    esc.channels = keys
    esc.save(update_fields=["recipients", "channels"])
    _timeline(inc, IncidentUpdate.Kind.ESCALATED, _("Escalated (%(r)s): %(n)s people, %(c)s channels") % {
        "r": rule.name, "n": n, "c": sent}, data={"rule": str(rule.pk)})
    system_log(inc.event, _("Incident #%(n)s escalated: %(r)s") % {"n": inc.number, "r": rule.name},
               source="incident.escalated", incident=inc, important=True)
    log(action="ops.incident_escalated", target=inc, event=inc.event,
        message=f"Incident #{inc.number} escalated by rule {rule.name}", changes={"recipients": n, "channels": sent})
    webhooks.emit("incident.escalated", {**payload_of(inc), "rule": rule.name}, event=inc.event)
    return True


def escalate_due(now: dt.datetime | None = None) -> int:
    """Beat task: every open incident of an event with escalation rules."""
    events = EscalationRule.objects.filter(enabled=True).values_list("event_id", flat=True).distinct()
    n = 0
    for pk in Incident.objects.filter(event_id__in=list(events), status__in=Incident.OPEN).values_list("pk",
                                                                                                         flat=True):
        n += escalate(pk, now)
    return n


def save_rule(rule: EscalationRule, *, actor: Any, request: Any = None, roles: list[Any] | None = None) -> None:
    created = rule._state.adding
    if not rule.name.strip():
        raise ValidationError(_("Give the rule a name."))
    rule.save()
    if roles is not None:
        rule.roles.set(roles)
    log(action="ops.escalation_rule_created" if created else "ops.escalation_rule_edited", actor=actor, target=rule,
        event=rule.event, request=request, message=rule.name,
        changes={"min_severity": rule.min_severity, "after_minutes": rule.after_minutes, "channels": rule.channels})


def delete_rule(rule: EscalationRule, *, actor: Any, request: Any = None) -> None:
    log(action="ops.escalation_rule_deleted", actor=actor, target=rule, event=rule.event, request=request,
        message=rule.name)
    rule.delete()


# ------------------------------------------------------------------ reports
def report_rows(event: Any) -> list[dict[str, Any]]:
    """One row per incident for the post-event report (CSV/JSON)."""
    out = []
    for inc in Incident.objects.filter(event=event).select_related("zone", "room", "assignee").order_by("number"):
        out.append({"number": inc.number, "title": inc.title, "category": inc.category, "severity": inc.severity,
                    "status": inc.status, "place": _place(inc), "team": inc.team,
                    "assignee": str(inc.assignee) if inc.assignee_id else "", "reported_by": inc.reported_by,
                    "created_at": inc.created_at.isoformat(),
                    "acknowledged_at": inc.acknowledged_at.isoformat() if inc.acknowledged_at else "",
                    "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else "",
                    "closed_at": inc.closed_at.isoformat() if inc.closed_at else "",
                    "minutes_to_acknowledge": round((inc.acknowledged_at - inc.created_at).total_seconds() / 60, 1)
                    if inc.acknowledged_at else "",
                    "minutes_to_resolve": round((inc.resolved_at - inc.created_at).total_seconds() / 60, 1)
                    if inc.resolved_at else "",
                    "description": inc.description})
    return out
