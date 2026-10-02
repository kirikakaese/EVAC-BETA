# SPDX-License-Identifier: AGPL-3.0-or-later
"""Django forms generated from JSON schemas (settings namespaces, extension settings, widget settings).

Supported property types: string (``enum``, ``format``: uri/email/color/password, ``x-widget``: textarea),
integer, number, boolean, array of enum strings (checkboxes) and array of strings (one per line).

With ``inherit=True`` every field gets a companion checkbox ``<name>__inherit``: checked = do not set the
value at this level (it is inherited from a more general level). :meth:`SchemaForm.values` returns only
the values set at this level.
"""
from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from . import settings_schema


class ColorInput(forms.TextInput):
    input_type = "color"


def field_for(name: str, prop: dict[str, Any], *, required: bool) -> forms.Field:
    label = prop.get("title") or name.replace("_", " ").capitalize()
    help_text = prop.get("description", "")
    typ = prop.get("type", "string")
    common = {"label": label, "help_text": help_text, "required": required}
    if "enum" in prop:
        labels = prop.get("x-enum-labels") or prop["enum"]
        return forms.ChoiceField(choices=list(zip(prop["enum"], labels, strict=False)), **common)
    if typ == "boolean":
        return forms.BooleanField(label=label, help_text=help_text, required=False)
    if typ == "integer":
        return forms.IntegerField(min_value=prop.get("minimum"), max_value=prop.get("maximum"), **common)
    if typ == "number":
        return forms.FloatField(min_value=prop.get("minimum"), max_value=prop.get("maximum"), **common)
    if typ == "array":
        items = prop.get("items", {})
        if "enum" in items:
            labels = items.get("x-enum-labels") or items["enum"]
            return forms.MultipleChoiceField(choices=list(zip(items["enum"], labels, strict=False)),
                                             widget=forms.CheckboxSelectMultiple, **common)
        return forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), **{
            **common, "help_text": (help_text + " " if help_text else "") + str(_("One entry per line."))})
    fmt = prop.get("format")
    max_length = prop.get("maxLength")
    if fmt == "uri":
        return forms.URLField(max_length=max_length, assume_scheme="https", **common)
    if fmt == "email":
        return forms.EmailField(max_length=max_length, **common)
    if fmt == "color":
        return forms.CharField(widget=ColorInput, max_length=7, **common)
    if prop.get("x-widget") == "textarea":
        return forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), max_length=max_length, **common)
    return forms.CharField(max_length=max_length, **common)


class SchemaForm(forms.Form):
    def __init__(self, *args, schema: dict[str, Any], initial_values: dict[str, Any] | None = None,
                 inherit: bool = False, resolved: settings_schema.Resolved | None = None, level: str = "",
                 **kwargs):
        self.schema = schema
        self.inherit = inherit
        self.level = level
        self.resolved = resolved
        initial_values = dict(initial_values or {})
        initial = {}
        for name, prop in settings_schema.properties(schema).items():
            value = initial_values.get(name, (resolved.values.get(name) if resolved else prop.get("default")))
            if prop.get("type") == "array" and "enum" not in prop.get("items", {}) and isinstance(value, list):
                value = "\n".join(str(v) for v in value)
            initial[name] = value
            if inherit:
                initial[f"{name}__inherit"] = name not in initial_values
        kwargs.setdefault("initial", initial)
        super().__init__(*args, **kwargs)
        required = set(schema.get("required", [])) if not inherit else set()
        for name, prop in settings_schema.properties(schema).items():
            self.fields[name] = field_for(name, dict(prop), required=name in required)
            if inherit:
                self.fields[name].required = False
                src = resolved.source.get(name, "default") if resolved else "default"
                self.fields[f"{name}__inherit"] = forms.BooleanField(
                    required=False, label=_("Inherit"),
                    help_text=_("Use the value from %(src)s") % {"src": src if src != level else _("the level above")})

    def rows(self):
        """``[(field, inherit_field, source_level)]`` for the template."""
        out = []
        for name in settings_schema.properties(self.schema):
            src = self.resolved.source.get(name, "default") if self.resolved else ""
            out.append((self[name], self[f"{name}__inherit"] if self.inherit else None, src))
        return out

    def values(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for name, prop in settings_schema.properties(self.schema).items():
            if self.inherit and self.cleaned_data.get(f"{name}__inherit"):
                continue
            raw = self.cleaned_data.get(name)
            if raw in (None, "") and prop.get("type") not in ("boolean", "string"):
                continue
            data[name] = settings_schema.coerce(prop, raw)
        return data

    def clean(self):
        cleaned = super().clean()
        if not self.errors:
            for err in settings_schema.validate(self.schema, self.values()):
                self.add_error(None, err)
        return cleaned
