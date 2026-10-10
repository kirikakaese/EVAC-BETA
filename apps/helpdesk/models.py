# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpdesk (brief §11.7, ADR-0043): lost & found, requests from visitors and crew, and the FAQ.

Lost reports and found items share one model (``LostFound.kind``) so matching is one query. Contact details of
visitors are only shown to helpdesk staff; the public page lists found items by what, category, colour and day
only. Visitors who report something get a status link (``token``) instead of an account.
"""
from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def _token() -> str:
    return secrets.token_urlsafe(16)


def _photo_path(instance: models.Model, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()[:5] if "." in filename else "jpg"
    return f"helpdesk/{instance.event_id}/{uuid.uuid4().hex}.{ext}"  # type: ignore[attr-defined]


CATEGORIES = [
    ("bag", _("Bag or backpack")), ("clothing", _("Clothing")), ("electronics", _("Phone or electronics")),
    ("keys", _("Keys")), ("wallet", _("Wallet, cards or documents")), ("jewellery", _("Jewellery or watch")),
    ("glasses", _("Glasses")), ("bottle", _("Bottle or cup")), ("toy", _("Toy")), ("other", _("Something else")),
]


class FaqEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="faq_entries")
    question = models.CharField(_("question"), max_length=200)
    answer = models.TextField(_("answer"))
    topic = models.CharField(_("topic"), max_length=60, blank=True, help_text=_("Groups the questions."))
    order = models.PositiveIntegerField(_("order"), default=0)
    public = models.BooleanField(_("on the public help page"), default=True)
    on_screens = models.BooleanField(_("on screens"), default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["topic", "order", "question"]

    def __str__(self):
        return self.question


class LostFound(models.Model):
    class Kind(models.TextChoices):
        LOST = "lost", _("Lost")
        FOUND = "found", _("Found")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        MATCHED = "matched", _("Matched")
        RETURNED = "returned", _("Returned")
        CLOSED = "closed", _("Closed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="lost_found")
    kind = models.CharField(max_length=5, choices=Kind.choices)
    reference = models.CharField(max_length=12)
    what = models.CharField(_("what"), max_length=120, help_text=_("e.g. Black backpack"))
    category = models.CharField(_("category"), max_length=12, choices=CATEGORIES, default="other")
    colour = models.CharField(_("colour"), max_length=40, blank=True)
    description = models.TextField(_("details"), blank=True,
                                   help_text=_("Brand, contents, marks. Not shown on the public page."))
    where = models.CharField(_("where"), max_length=120, blank=True)
    room = models.ForeignKey("venues.Room", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                             verbose_name=_("room"))
    when = models.DateTimeField(_("when"), null=True, blank=True)
    photo = models.ImageField(_("photo"), upload_to=_photo_path, blank=True)
    storage = models.CharField(_("kept at"), max_length=120, blank=True, help_text=_("e.g. Helpdesk box 3"))
    name = models.CharField(_("name"), max_length=120, blank=True)
    contact = models.CharField(_("contact"), max_length=200, blank=True,
                               help_text=_("Phone or e-mail, only for the helpdesk."))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    match = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    handed_to = models.CharField(_("handed to"), max_length=120, blank=True)
    handed_at = models.DateTimeField(null=True, blank=True)
    handed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    public = models.BooleanField(_("list publicly"), default=True,
                                 help_text=_("Found items: what, category, colour and day on the public page."))
    source = models.CharField(max_length=10, default="staff")
    token = models.CharField(max_length=32, default=_token, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "reference"], name="helpdesk_lf_reference")]

    def __str__(self):
        return f"{self.reference} {self.what}"


class Ticket(models.Model):
    class Status(models.TextChoices):
        NEW = "new", _("New")
        OPEN = "open", _("In progress")
        WAITING = "waiting", _("Waiting")
        DONE = "done", _("Done")

    CATEGORIES = [("question", _("Question")), ("problem", _("Problem")), ("accessibility", _("Accessibility")),
                  ("feedback", _("Feedback")), ("other", _("Other"))]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="tickets")
    reference = models.CharField(max_length=12)
    subject = models.CharField(_("subject"), max_length=160)
    body = models.TextField(_("message"))
    category = models.CharField(_("about"), max_length=14, choices=CATEGORIES, default="question")
    name = models.CharField(_("name"), max_length=120, blank=True)
    contact = models.CharField(_("contact"), max_length=200, blank=True,
                               help_text=_("Phone or e-mail if you want an answer."))
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.NEW)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+", verbose_name=_("assigned to"))
    source = models.CharField(max_length=10, default="staff")
    token = models.CharField(max_length=32, default=_token, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "reference"], name="helpdesk_ticket_reference")]

    def __str__(self):
        return f"{self.reference} {self.subject}"

    @property
    def is_open(self) -> bool:
        return self.status != self.Status.DONE


class TicketNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="notes")
    text = models.TextField()
    public = models.BooleanField(default=False, help_text="A reply the requester sees on the status page.")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at"]
