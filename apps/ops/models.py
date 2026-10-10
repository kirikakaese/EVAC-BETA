# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operations (brief §11.3, ADR-0039): incidents with a timeline, the radio-style ops log, tasks and escalation
rules.

Incidents carry a per-event number (#1, #2, …), a category and a severity, a place (zone, room, free text) and a
status. Everything that happens to one is a row in its timeline (``IncidentUpdate``). The ops log is the control
room's running record: people write entries ("Security 2 → Control: gate C clear") and the system adds entries for
alarms, offline screens, DECT alerts and the like. Escalation rules notify roles and channels when an incident of a
severity stays unacknowledged.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class Incident(models.Model):
    class Severity(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")
        CRITICAL = "critical", _("Critical")

    class Status(models.TextChoices):
        NEW = "new", _("New")
        ACKNOWLEDGED = "acknowledged", _("Acknowledged")
        IN_PROGRESS = "in_progress", _("In progress")
        RESOLVED = "resolved", _("Resolved")
        CLOSED = "closed", _("Closed")

    OPEN = (Status.NEW, Status.ACKNOWLEDGED, Status.IN_PROGRESS)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="incidents")
    number = models.PositiveIntegerField(_("number"))
    title = models.CharField(_("title"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    category = models.CharField(_("category"), max_length=40, default="other")
    severity = models.CharField(_("severity"), max_length=10, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.NEW)
    zone = models.ForeignKey("venues.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("zone"))
    room = models.ForeignKey("venues.Room", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("room"))
    location = models.CharField(_("where exactly"), max_length=200, blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+", verbose_name=_("assigned to"))
    team = models.CharField(_("team"), max_length=80, blank=True, help_text=_("e.g. Security, Medics"))
    reported_by = models.CharField(_("reported by"), max_length=120, blank=True,
                                   help_text=_("Who reported it (a name, a radio call sign, a phone number)."))
    #: links to things of other modules: [{"kind": "announcement", "id": "…", "label": "…", "url": "…"}]
    links = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=60, blank=True, help_text="manual, api, dial, …")
    external_id = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "number"], name="ops_incident_number")]
        indexes = [models.Index(fields=["event", "status"])]

    def __str__(self):
        return f"#{self.number} {self.title}"

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN

    @property
    def place(self) -> str:
        """The room, else the zone (names), for lists."""
        return self.room.name if self.room_id else (self.zone.name if self.zone_id else "")

    @property
    def rank(self) -> int:
        return SEVERITY_RANK.get(self.severity, 0)

    def evac_scope_chain(self) -> list[tuple[str, str]]:
        """Scoped permissions: an incident in a zone (or a room in zones) can be handled by that zone's team."""
        chain: list[tuple[str, str]] = []
        if self.zone_id:
            chain.append(("zone", str(self.zone_id)))
        if self.room_id:
            chain.append(("room", str(self.room_id)))
            chain += [("zone", str(z)) for z in self.room.zones.values_list("pk", flat=True)]
        return chain


def attachment_path(instance: IncidentUpdate, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()[:8] if "." in filename else "bin"
    return f"ops/{instance.incident.event_id}/{instance.incident_id}/{uuid.uuid4().hex}.{ext}"


class IncidentUpdate(models.Model):
    """One line of an incident's timeline."""

    class Kind(models.TextChoices):
        CREATED = "created", _("Created")
        NOTE = "note", _("Note")
        STATUS = "status", _("Status")
        ASSIGNED = "assigned", _("Assigned")
        SEVERITY = "severity", _("Severity")
        EDITED = "edited", _("Edited")
        ESCALATED = "escalated", _("Escalated")
        LINK = "link", _("Linked")
        ATTACHMENT = "attachment", _("Attachment")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="updates")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    text = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    attachment = models.FileField(upload_to=attachment_path, blank=True, max_length=300)
    attachment_name = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at"]


class LogEntry(models.Model):
    """The ops log: radio-style entries by people, plus entries the system writes (alarms, screens, DECT …)."""

    class Kind(models.TextChoices):
        MESSAGE = "message", _("Message")
        SYSTEM = "system", _("System")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="ops_log")
    at = models.DateTimeField(db_index=True)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.MESSAGE)
    sender = models.CharField(_("from"), max_length=80, blank=True, help_text=_("e.g. Security 2"))
    recipient = models.CharField(_("to"), max_length=80, blank=True, help_text=_("e.g. Control"))
    text = models.TextField(_("message"))
    important = models.BooleanField(_("important"), default=False)
    source = models.CharField(max_length=80, blank=True, help_text="system entries: the event type")
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name="log",
                                 verbose_name=_("incident"))
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+")
    client_id = models.CharField(max_length=64, blank=True, help_text="idempotency key of offline entries")

    class Meta:
        ordering = ["-at"]
        constraints = [models.UniqueConstraint(fields=["event", "client_id"], condition=~models.Q(client_id=""),
                                               name="ops_log_client_id")]


class Task(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        DONE = "done", _("Done")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="ops_tasks")
    title = models.CharField(_("task"), max_length=200)
    notes = models.TextField(_("notes"), blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+", verbose_name=_("assigned to"))
    team = models.CharField(_("team"), max_length=80, blank=True)
    due_at = models.DateTimeField(_("due"), null=True, blank=True)
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks",
                                 verbose_name=_("incident"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    done_at = models.DateTimeField(null=True, blank=True)
    done_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+")

    class Meta:
        ordering = ["status", "due_at", "created_at"]

    def __str__(self):
        return self.title


class EscalationRule(models.Model):
    """When an incident of at least ``min_severity`` (and one of ``categories``) has been open ``after_minutes``
    without being acknowledged (``unacknowledged``) or resolved, notify the roles' members and send to channels."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="escalation_rules")
    name = models.CharField(_("name"), max_length=120)
    enabled = models.BooleanField(_("enabled"), default=True)
    min_severity = models.CharField(_("from severity"), max_length=10, choices=Incident.Severity.choices,
                                    default=Incident.Severity.HIGH)
    categories = models.JSONField(_("categories"), default=list, blank=True, help_text=_("Empty: all categories."))
    after_minutes = models.PositiveIntegerField(_("after (minutes)"), default=0,
                                                help_text=_("0: as soon as the incident is reported."))
    until = models.CharField(_("while the incident is"), max_length=14, default="unacknowledged",
                             choices=[("unacknowledged", _("not acknowledged")), ("unresolved", _("not resolved"))])
    roles = models.ManyToManyField("events.Role", blank=True, related_name="+", verbose_name=_("notify roles"))
    channels = models.JSONField(_("channels"), default=list, blank=True,
                                help_text=_("Notification channels (ntfy, Matrix, e-mail, …) of this event."))
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["after_minutes", "order", "name"]

    def __str__(self):
        return self.name


class Escalation(models.Model):
    """A rule that fired for an incident (each rule fires once per incident)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="escalations")
    rule = models.ForeignKey(EscalationRule, null=True, on_delete=models.SET_NULL, related_name="+")
    rule_name = models.CharField(max_length=120)
    at = models.DateTimeField(auto_now_add=True)
    recipients = models.PositiveIntegerField(default=0)
    channels = models.JSONField(default=list)

    class Meta:
        ordering = ["at"]
        constraints = [models.UniqueConstraint(fields=["incident", "rule"], name="ops_escalation_once")]


#: for the OpenAPI enum name (``ENUM_NAME_OVERRIDES``: nested classes cannot be named by an import string)
INCIDENT_STATUS = Incident.Status
