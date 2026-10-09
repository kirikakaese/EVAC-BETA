# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.utils.translation import gettext_lazy as _

from . import engine


class UploadForm(forms.Form):
    file = forms.FileField(label=_("Pack file"), widget=forms.ClearableFileInput(attrs={"accept": ".evacpack,.zip"}))


class UrlForm(forms.Form):
    url = forms.URLField(label=_("Pack URL"), max_length=1000, assume_scheme="https",
                         help_text=_("Downloaded by the server, then shown for review before anything is imported."))


class ExportForm(forms.Form):
    name = forms.CharField(label=_("Pack name"), max_length=200)
    description = forms.CharField(label=_("Description"), required=False, max_length=2000,
                                  widget=forms.Textarea(attrs={"rows": 2}))
    sign = forms.BooleanField(label=_("Sign the pack with this server's key"), required=False, initial=True,
                              help_text=_("Lets other servers check where the pack comes from and that it was not "
                                          "changed."))

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.section_fields = []
        for spec in engine.sections(event):
            choices = spec.choices(event)
            if not choices:
                continue
            name = f"s_{spec.key}"
            self.fields[name] = forms.MultipleChoiceField(label=spec.title, required=False, choices=choices,
                                                          widget=forms.CheckboxSelectMultiple)
            self.section_fields.append(name)

    def selection(self) -> dict[str, set[str]]:
        return {n[2:]: set(self.cleaned_data.get(n) or []) for n in self.section_fields}

    def clean(self):
        data = super().clean()
        if not any(data.get(n) for n in self.section_fields):
            raise forms.ValidationError(_("Choose at least one thing to export."))
        return data


class TrustForm(forms.Form):
    public_key = forms.CharField(label=_("Public key"), max_length=64,
                                 help_text=_("The other server shows it under Settings → Pack keys."))
    name = forms.CharField(label=_("Name"), max_length=200, help_text=_("Who this key belongs to."))
