# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .models import FaqEntry, LostFound, Ticket

DT = {"widget": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
      "input_formats": ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]}


class _Honeypot(forms.Form):
    """A field people do not see (spam guard); a bot that fills it is ignored."""

    website = forms.CharField(label=_("Leave this empty"), required=False,
                              widget=forms.TextInput(attrs={"class": "hp", "autocomplete": "off", "tabindex": "-1"}))


class LostFoundForm(forms.ModelForm):
    when = forms.DateTimeField(label=_("When"), required=False, **DT)  # type: ignore[arg-type]

    class Meta:
        model = LostFound
        fields = ["what", "category", "colour", "description", "where", "room", "when", "photo", "storage", "name",
                  "contact", "public"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        from apps.venues.models import Room

        self.fields["room"].queryset = Room.objects.filter(venue__in=event.venues.all())
        if self.instance.kind == LostFound.Kind.LOST:
            del self.fields["storage"]
            del self.fields["public"]
            self.fields["where"].help_text = _("Where it was probably lost.")
        else:
            self.fields["name"].label = _("Found by")
            self.fields["contact"].help_text = _("Of the finder, if they want to be told.")


class PublicLostForm(_Honeypot, forms.ModelForm):
    when = forms.DateTimeField(label=_("When (about)"), required=False, **DT)  # type: ignore[arg-type]

    class Meta:
        model = LostFound
        fields = ["what", "category", "colour", "description", "where", "when", "name", "contact"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.fields["contact"].required = True
        self.fields["description"].help_text = _("Brand, contents, marks: helps us find it. Only the helpdesk sees "
                                                 "this.")


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["category", "subject", "body", "name", "contact"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}


class PublicTicketForm(_Honeypot, TicketForm):
    pass


class UpdateForm(forms.Form):
    status = forms.ChoiceField(label=_("Status"), choices=Ticket.Status.choices)
    assignee = forms.ModelChoiceField(label=_("Assigned to"), queryset=get_user_model().objects.none(),
                                      required=False)
    note = forms.CharField(label=_("Note"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    public = forms.BooleanField(label=_("Reply: the requester sees it on their status page"), required=False)

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = get_user_model().objects.filter(memberships__event=event, is_active=True)


class FaqForm(forms.ModelForm):
    class Meta:
        model = FaqEntry
        fields = ["question", "answer", "topic", "order", "public", "on_screens"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 3})}
