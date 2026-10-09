# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.utils.translation import gettext_lazy as _

from . import mapping, services
from .models import CustomWidget, Feed

FIELD_LABELS = {"title": _("Title"), "subtitle": _("Subtitle"), "value": _("Value (number)"), "label": _("Label"),
                "time": _("Time"), "end": _("End time"), "image": _("Image URL"), "link": _("Link")}


class FeedForm(forms.ModelForm):
    auth_header = forms.CharField(
        label=_("Authorization header"), required=False, max_length=500, widget=forms.PasswordInput(render_value=False),
        help_text=_("Optional, e.g. “Authorization: Bearer abc” or “X-Api-Key: abc”. Stored encrypted; leave empty to "
                    "keep the stored one."))
    clear_auth = forms.BooleanField(label=_("Remove the stored header"), required=False)

    class Meta:
        model = Feed
        fields = ["name", "kind", "url", "source", "poll_seconds", "enabled"]

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event
        choices = services.source_choices(event)
        self.fields["source"] = forms.ChoiceField(label=_("EVAC data source"), required=False,
                                                  choices=[("", "—"), *choices],
                                                  help_text=_("Only for the type “EVAC data source”."))
        self.fields["url"].help_text = _("For JSON, RSS, iCal and CSV. Google Sheets: File → Share → Publish to web → "
                                         "CSV.")
        self.fields["poll_seconds"].widget.attrs.update(min=services.MIN_POLL, max=86400)
        if not self.instance.auth_header_encrypted:
            del self.fields["clear_auth"]

    def auth_value(self) -> str | None:
        if self.cleaned_data.get("clear_auth"):
            return ""
        value = self.cleaned_data.get("auth_header", "")
        return value if value else None


class WidgetForm(forms.ModelForm):
    limit = forms.IntegerField(label=_("Items at most"), min_value=1, max_value=mapping.MAX_ROWS, initial=10)
    heading = forms.CharField(label=_("Heading"), required=False, max_length=120)
    template = forms.CharField(label=_("Text"), required=False, max_length=500,
                               help_text=_("Only for the visual “Text”: {{ data.first.title }}, {{ data.first.value }}"
                                           " or {{ data.count }}."))
    unit = forms.CharField(label=_("Unit"), required=False, max_length=20)
    minimum = forms.FloatField(label=_("Gauge minimum"), required=False, initial=0)
    maximum = forms.FloatField(label=_("Gauge maximum"), required=False, initial=100)
    upcoming = forms.BooleanField(label=_("Hide items that are over"), required=False,
                                  help_text=_("Uses the end time, otherwise the time of each item."))

    OPTION_FIELDS = ("limit", "heading", "template", "unit", "minimum", "maximum", "upcoming")

    class Meta:
        model = CustomWidget
        fields = ["name", "feed", "visual", "items_path"]

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event
        self.fields["feed"].queryset = Feed.objects.filter(event=event)
        for name in mapping.FIELDS:
            self.fields[f"f_{name}"] = forms.CharField(
                label=FIELD_LABELS[name], required=False, max_length=300,
                initial=(self.instance.fields or {}).get(name, ""),
                help_text=_("Path inside one item, e.g. name or author.name") if name == "title" else "")
        opts = self.instance.options or {}
        for name in self.OPTION_FIELDS:
            if name in opts:
                self.fields[name].initial = opts[name]

    def field_paths(self):
        return [self[f"f_{n}"] for n in mapping.FIELDS]

    def option_fields(self):
        return [self[n] for n in self.OPTION_FIELDS]

    def main_fields(self):
        return [self[n] for n in ("name", "feed", "visual", "items_path")]

    def clean(self):
        cleaned = super().clean()
        for name in ["items_path", *(f"f_{n}" for n in mapping.FIELDS)]:
            value = (cleaned.get(name) or "").strip()
            if value:
                try:
                    mapping.tokens(value)
                except mapping.PathError as exc:
                    self.add_error(name, str(exc))
        return cleaned

    def build(self) -> CustomWidget:
        w = self.save(commit=False)
        w.fields = {n: self.cleaned_data[f"f_{n}"].strip() for n in mapping.FIELDS
                    if self.cleaned_data.get(f"f_{n}", "").strip()}
        w.options = {n: self.cleaned_data[n] for n in self.OPTION_FIELDS
                     if self.cleaned_data.get(n) not in (None, "")}
        return w
