# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .models import Category, Item, Loan


class ItemForm(forms.ModelForm):
    copies = forms.IntegerField(label=_("How many"), min_value=1, max_value=200, initial=1, required=False,
                                help_text=_("Several identical items (e.g. 20 radios) get consecutive tags."))

    class Meta:
        model = Item
        fields = ["name", "category", "asset_tag", "serial", "room", "location", "description", "photo"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        from apps.venues.models import Room

        self.fields["category"].queryset = Category.objects.filter(event=event)
        self.fields["room"].queryset = Room.objects.filter(venue__in=event.venues.all())
        self.fields["asset_tag"].required = False
        if not self.instance._state.adding:
            del self.fields["copies"]


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "loan_hours"]


class LendForm(forms.Form):
    borrower = forms.CharField(label=_("Lent to"), max_length=120, required=False,
                               help_text=_("A name, or choose an account below."))
    borrower_user = forms.ModelChoiceField(label=_("Account"), queryset=get_user_model().objects.none(),
                                           required=False)
    contact = forms.CharField(label=_("Contact"), max_length=120, required=False,
                              help_text=_("Phone, DECT or team."))
    due_at = forms.DateTimeField(label=_("Due back"), required=False,
                                 widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                                 input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"])
    photo = forms.ImageField(label=_("Photo"), required=False, help_text=_("Optional: the item as it leaves."),
                             widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}))
    signature = forms.CharField(required=False, widget=forms.HiddenInput(attrs={"data-signature-value": ""}))

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.fields["borrower_user"].queryset = get_user_model().objects.filter(memberships__event=event,
                                                                                is_active=True)

    def clean(self) -> dict[str, Any]:
        data = super().clean()
        if not data.get("borrower") and not data.get("borrower_user"):
            raise forms.ValidationError(_("Who gets it?"))
        return data


class ReturnForm(forms.Form):
    condition = forms.ChoiceField(label=_("Condition"), choices=Loan.Condition.choices, initial="ok")
    notes = forms.CharField(label=_("Note"), required=False, max_length=500)
    photo = forms.ImageField(label=_("Photo"), required=False,
                             widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}))


class NoteForm(forms.Form):
    kind = forms.ChoiceField(label=_("Kind"), choices=[("note", _("Note")), ("maintenance", _("Maintenance")),
                                                       ("damage", _("Damage"))])
    text = forms.CharField(label=_("Text"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    status = forms.ChoiceField(label=_("Set status"), required=False,
                               choices=[("", "–"), *[(k, v) for k, v in Item.Status.choices if k != "lent"]])
