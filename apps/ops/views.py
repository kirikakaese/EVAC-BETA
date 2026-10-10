# SPDX-License-Identifier: AGPL-3.0-or-later
"""Incident pages, the ops log, tasks, escalation rules and the incident report (ADR-0039)."""
from __future__ import annotations

import csv
import datetime as dt
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import services
from .forms import EscalationRuleForm, IncidentForm, LogEntryForm, NoteForm, StatusForm, TaskForm
from .models import EscalationRule, Incident, IncidentUpdate, LogEntry, Task

MODULE = "ops"


def _fail(request: Any, err: ValidationError) -> None:
    for msg in err.messages:
        messages.error(request, msg)


def _can(request: Any, event: Any, perm: str, obj: Any = None) -> bool:
    return rbac.has_perm(request.user, event, perm, obj=obj, request=request)


def _incident(event: Any, pk: Any) -> Incident:
    return get_object_or_404(Incident.objects.select_related("zone", "room", "assignee", "created_by"), event=event,
                             pk=pk)


# ------------------------------------------------------------------ incidents
@event_view("ops.view", module=MODULE)
def index(request, slug, *, event):
    qs = Incident.objects.filter(event=event).select_related("zone", "room", "assignee")
    show = request.GET.get("show", "open")
    if show == "open":
        qs = qs.filter(status__in=Incident.OPEN)
    elif show in Incident.Status.values:
        qs = qs.filter(status=show)
    severity = request.GET.get("severity", "")
    if severity in Incident.Severity.values:
        qs = qs.filter(severity=severity)
    category = request.GET.get("category", "")
    if category:
        qs = qs.filter(category=category)
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(location__icontains=q) | Q(description__icontains=q))
    rows = sorted(qs, key=lambda i: (not i.is_open, -i.rank, -(i.created_at.timestamp())))
    counts = {s: Incident.objects.filter(event=event, status=s).count() for s in Incident.Status.values}
    return render(request, "ops/index.html", {
        "event": event, "incidents": rows[:500], "show": show, "severity": severity, "category": category, "q": q,
        "categories": services.categories(event), "tabs": [(k, lbl, counts[k]) for k, lbl in Incident.Status.choices],
        "severities": Incident.Severity.choices, "counts": counts,
        "open_count": sum(counts[s] for s in Incident.OPEN),
        "can_report": _can(request, event, "ops.report"), "can_export": _can(request, event, "ops.export")})


@event_view("ops.report", module=MODULE)
def new(request, slug, *, event):
    form = IncidentForm(request.POST or None, instance=Incident(event=event), event=event)
    if request.method == "POST" and form.is_valid():
        inc = form.save(commit=False)
        inc.source = "manual"
        try:
            services.create_incident(inc, actor=request.user, request=request, note=form.cleaned_data.get("note", ""))
        except ValidationError as err:
            _fail(request, err)
        else:
            messages.success(request, _("Incident #%(n)s reported.") % {"n": inc.number})
            return redirect("ops:incident", slug, inc.pk)
    return render(request, "ops/incident_form.html", {"event": event, "form": form, "obj": None})


@event_view("ops.view", module=MODULE)
def incident(request, slug, pk, *, event):
    inc = _incident(event, pk)
    can_manage = _can(request, event, "ops.manage", inc)
    nexts = [(s, Incident.Status(s).label) for s in Incident.Status.values
             if s in services.TRANSITIONS.get(inc.status, set())]
    return render(request, "ops/incident.html", {
        "event": event, "inc": inc, "updates": inc.updates.select_related("actor"),
        "tasks": inc.tasks.select_related("assignee"), "log": inc.log.all()[:30],
        "escalations": inc.escalations.all(), "nexts": nexts, "can_manage": can_manage,
        "can_note": can_manage or _can(request, event, "ops.report"),
        "note_form": NoteForm(), "task_form": TaskForm(event=event, initial={"incident": inc.pk}),
        "status_form": StatusForm()})


@event_view("ops.manage", module=MODULE)
def edit(request, slug, pk, *, event):
    inc = _incident(event, pk)
    if not _can(request, event, "ops.manage", inc):
        raise PermissionDenied("ops.manage")
    before = {f: getattr(inc, f) for f in services.EDITABLE}
    form = IncidentForm(request.POST or None, instance=inc, event=event)
    if request.method == "POST" and form.is_valid():
        try:
            services.update_incident(form.save(commit=False), list(form.changed_data), actor=request.user,
                                     request=request, before=before)
        except ValidationError as err:
            _fail(request, err)
        else:
            messages.success(request, _("Saved."))
            return redirect("ops:incident", slug, inc.pk)
    return render(request, "ops/incident_form.html", {"event": event, "form": form, "obj": inc})


@require_POST
@event_view("ops.view", module=MODULE)
def status(request, slug, pk, *, event):
    inc = _incident(event, pk)
    target = request.POST.get("status", "")
    # whoever may report may also acknowledge ("I'm on it"); everything else needs ops.manage
    perm = "ops.report" if target == Incident.Status.ACKNOWLEDGED and inc.status == Incident.Status.NEW \
        else "ops.manage"
    if not (_can(request, event, "ops.manage", inc) or _can(request, event, perm, inc)):
        raise PermissionDenied(perm)
    try:
        services.set_status(inc, target, actor=request.user, request=request,
                            note=(request.POST.get("note") or "").strip()[:500])
    except ValidationError as err:
        _fail(request, err)
    else:
        messages.success(request, _("Incident #%(n)s: %(s)s.") % {"n": inc.number, "s": inc.get_status_display()})
    return redirect(request.POST.get("next") or f"{_url(event, inc)}")


def _url(event: Any, inc: Incident) -> str:
    from django.urls import reverse

    return reverse("ops:incident", args=[event.slug, inc.pk])


@require_POST
@event_view("ops.view", module=MODULE)
def note(request, slug, pk, *, event):
    inc = _incident(event, pk)
    if not (_can(request, event, "ops.manage", inc) or _can(request, event, "ops.report", inc)):
        raise PermissionDenied("ops.report")
    form = NoteForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            services.add_note(inc, form.cleaned_data["text"], actor=request.user, request=request,
                              attachment=form.cleaned_data.get("attachment"))
        except ValidationError as err:
            _fail(request, err)
    else:
        messages.error(request, _("The note could not be saved."))
    return redirect("ops:incident", slug, inc.pk)


@event_view("ops.view", module=MODULE)
def attachment(request, slug, pk, *, event):
    u = get_object_or_404(IncidentUpdate.objects.select_related("incident"), pk=pk, incident__event=event)
    if not u.attachment:
        raise Http404
    resp = FileResponse(u.attachment.open("rb"), as_attachment=not u.attachment_name.lower().endswith(
        (".jpg", ".jpeg", ".png", ".webp", ".gif")), filename=u.attachment_name or "attachment")
    resp["Cache-Control"] = "private, max-age=300"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    return resp


# ------------------------------------------------------------------ ops log
@event_view("ops.view", module=MODULE)
def log_page(request, slug, *, event):
    can_write = _can(request, event, "ops.report")
    form = LogEntryForm(request.POST or None, event=event) if can_write else None
    if request.method == "POST":
        if not can_write:
            raise PermissionDenied("ops.report")
        if form.is_valid():
            try:
                services.add_entry(event, form.cleaned_data["text"], actor=request.user,
                                   sender=form.cleaned_data["sender"], recipient=form.cleaned_data["recipient"],
                                   important=form.cleaned_data["important"], incident=form.cleaned_data["incident"],
                                   client_id=request.POST.get("client_id", ""),
                                   at=parse_datetime(request.POST.get("written_at") or "") or None, request=request)
            except ValidationError as err:
                _fail(request, err)
            else:
                return redirect("ops:log", slug)
    qs = LogEntry.objects.filter(event=event).select_related("incident", "author")
    only = request.GET.get("only", "")
    if only == "important":
        qs = qs.filter(important=True)
    elif only in ("message", "system"):
        qs = qs.filter(kind=only)
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(text__icontains=q)
    page = Paginator(qs, 100).get_page(request.GET.get("page"))
    return render(request, "ops/log.html", {"event": event, "page": page, "form": form, "only": only, "q": q,
                                            "senders": _recent_names(event)})


def _recent_names(event: Any) -> list[str]:
    names = LogEntry.objects.filter(event=event, kind=LogEntry.Kind.MESSAGE).values_list("sender", "recipient")[:200]
    return sorted({n for pair in names for n in pair if n})[:40]


# ------------------------------------------------------------------ tasks
@event_view("ops.view", module=MODULE)
def tasks(request, slug, *, event):
    can_manage = _can(request, event, "ops.manage")
    form = TaskForm(request.POST or None, instance=Task(event=event), event=event) if can_manage else None
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied("ops.manage")
        if form.is_valid():
            with timezone.override(_tz(event)):
                try:
                    services.save_task(form.save(commit=False), actor=request.user, request=request)
                except ValidationError as err:
                    _fail(request, err)
                else:
                    messages.success(request, _("Task added."))
            nxt = request.POST.get("next") or ""
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else f"/e/{slug}/ops/tasks/")
    show = request.GET.get("show", "open")
    qs = Task.objects.filter(event=event).select_related("assignee", "incident")
    if show == "open":
        qs = qs.filter(status=Task.Status.OPEN)
    elif show == "mine":
        qs = qs.filter(assignee=request.user, status=Task.Status.OPEN)
    with timezone.override(_tz(event)):
        return render(request, "ops/tasks.html", {"event": event, "tasks": qs, "form": form, "show": show,
                                                  "can_manage": can_manage, "now": timezone.now()})


def _tz(event: Any) -> Any:
    import zoneinfo

    try:
        return zoneinfo.ZoneInfo(event.timezone or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return dt.UTC


@require_POST
@event_view("ops.view", module=MODULE)
def task_done(request, slug, pk, *, event):
    t = get_object_or_404(Task, event=event, pk=pk)
    if not (_can(request, event, "ops.manage") or t.assignee_id == request.user.pk):
        raise PermissionDenied("ops.manage")
    services.set_task_done(t, request.POST.get("done") == "1", actor=request.user, request=request)
    nxt = request.POST.get("next") or ""
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else f"/e/{slug}/ops/tasks/")


# ------------------------------------------------------------------ escalation
@event_view("ops.escalation", module=MODULE)
def rules(request, slug, pk=None, *, event):
    rule = get_object_or_404(EscalationRule, event=event, pk=pk) if pk else EscalationRule(event=event)
    form = EscalationRuleForm(request.POST or None, instance=rule, event=event)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        try:
            services.save_rule(obj, actor=request.user, request=request, roles=list(form.cleaned_data["roles"]))
        except ValidationError as err:
            _fail(request, err)
        else:
            messages.success(request, _("Escalation rule saved."))
            return redirect("ops:rules", slug)
    return render(request, "ops/rules.html", {
        "event": event, "form": form, "rule": rule if pk else None,
        "rules": EscalationRule.objects.filter(event=event).prefetch_related("roles")})


@require_POST
@event_view("ops.escalation", module=MODULE)
def rule_delete(request, slug, pk, *, event):
    services.delete_rule(get_object_or_404(EscalationRule, event=event, pk=pk), actor=request.user, request=request)
    messages.success(request, _("Escalation rule deleted."))
    return redirect("ops:rules", slug)


# ------------------------------------------------------------------ report
@event_view("ops.export", module=MODULE)
def export(request, slug, *, event):
    from apps.core.audit import log

    rows = services.report_rows(event)
    fmt = request.GET.get("format", "csv")
    log(action="ops.report_exported", actor=request.user, event=event, request=request,
        message=f"Incident report ({fmt}, {len(rows)} incidents)")
    if fmt == "json":
        log_rows = [{"at": e.at.isoformat(), "kind": e.kind, "from": e.sender, "to": e.recipient, "text": e.text,
                     "important": e.important, "incident": e.incident.number if e.incident_id else None}
                    for e in LogEntry.objects.filter(event=event).select_related("incident").order_by("at")]
        resp = JsonResponse({"event": event.slug, "generated": timezone.now().isoformat(), "incidents": rows,
                             "ops_log": log_rows})
        resp["Content-Disposition"] = f'attachment; filename="{event.slug}-incident-report.json"'
        return resp
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{event.slug}-incidents.csv"'
    fields = list(rows[0]) if rows else ["number", "title"]
    w = csv.DictWriter(resp, fieldnames=fields)
    w.writeheader()
    for row in rows:
        # no spreadsheet formulas from user text
        w.writerow({k: (f"'{v}" if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v)
                    for k, v in row.items()})
    return resp
