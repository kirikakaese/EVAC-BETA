# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .layout_format import PRESETS
from .models import Asset, AssetFolder, FontFamily, Layout, Theme, owner_q


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if isinstance(data, list | tuple):
            return [super(MultipleFileField, self).clean(d, initial) for d in data]
        return [super().clean(data, initial)] if data else []


class TagsField(forms.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("help_text", _("Comma separated."))
        super().__init__(**kwargs)

    def prepare_value(self, value):
        return ", ".join(value) if isinstance(value, list | tuple) else value

    def to_python(self, value):
        return [t.strip() for t in (value or "").split(",") if t.strip()]


def _shared_field(form, user):
    if user.is_superuser:
        form.fields["shared"] = forms.BooleanField(
            label=_("Add to the shared library"), required=False,
            help_text=_("Shared items can be used by every event of this EVAC."))


class AssetUploadForm(forms.Form):
    files = MultipleFileField(label=_("Files"), help_text=_(
        "Images (JPEG, PNG, GIF, WebP, AVIF, SVG), video (MP4, MOV, WebM, MKV), audio (MP3, M4A, WAV, OGG, FLAC), "
        "PDF and Lottie JSON."))
    folder = forms.ModelChoiceField(label=_("Folder"), queryset=AssetFolder.objects.none(), required=False)
    tags = TagsField(label=_("Tags"))

    def __init__(self, *args, event, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["folder"].queryset = AssetFolder.objects.filter(owner_q(event))
        _shared_field(self, user)


class AssetForm(forms.ModelForm):
    tags = TagsField(label=_("Tags"))

    class Meta:
        model = Asset
        fields = ["name", "alt_text", "credit", "folder", "tags"]

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["folder"].queryset = AssetFolder.objects.filter(owner_q(event))


class FolderForm(forms.ModelForm):
    class Meta:
        model = AssetFolder
        fields = ["name", "parent"]
        labels = {"name": _("New folder"), "parent": _("Inside")}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = AssetFolder.objects.filter(event=event)


class FontUploadForm(forms.Form):
    file = forms.FileField(label=_("Font file"), help_text=_("WOFF2, WOFF, TTF or OTF; variable fonts work too."))
    family = forms.ModelChoiceField(label=_("Add to family"), queryset=FontFamily.objects.none(), required=False,
                                    empty_label=_("A new family (name from the font)"))
    name = forms.CharField(label=_("Family name"), max_length=120, required=False,
                           help_text=_("Leave empty to use the name stored in the font."))
    category = forms.ChoiceField(label=_("Category"), choices=FontFamily.Category.choices)
    licence = forms.CharField(label=_("Licence note"), required=False, widget=forms.Textarea(attrs={"rows": 2}),
                              help_text=_("e.g. SIL Open Font License 1.1, bought licence for this event."))
    subset = forms.BooleanField(label=_("Keep Latin characters only (smaller file)"), required=False,
                                help_text=_("Includes arrows and common symbols. Leave off for other scripts."))

    def __init__(self, *args, event, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["family"].queryset = FontFamily.objects.filter(event=event, builtin=False)
        _shared_field(self, user)


class ThemeForm(forms.ModelForm):
    class Meta:
        model = Theme
        fields = ["name", "key", "description", "parent"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}
        help_texts = {"key": _("Short name, used to pick the theme (e.g. festival-dark).")}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.fields["key"].required = False
        qs = Theme.objects.filter(owner_q(event))
        if not self.instance._state.adding:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = qs
        self.fields["parent"].empty_label = _("EVAC defaults")

    def clean_key(self):
        key = slugify(self.cleaned_data.get("key") or self.cleaned_data.get("name") or "")[:64]
        if not key:
            key = "theme"
        owner = self.instance.event if not self.instance._state.adding else self.event
        clash = Theme.objects.filter(event=owner, key=key)
        if not self.instance._state.adding:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_("This short name is taken."))
        return key


class LayoutCreateForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=200)
    size = forms.ChoiceField(label=_("Screen size"), choices=[
        ("1920x1080", _("Full HD landscape 1920 × 1080")), ("1080x1920", _("Full HD portrait 1080 × 1920")),
        ("3840x2160", _("4K landscape 3840 × 2160")), ("1280x720", _("HD 1280 × 720")),
        ("1024x768", _("4:3 projector 1024 × 768")), ("3840x1080", _("32:9 LED strip 3840 × 1080")),
        ("1920x480", _("Ticker strip 1920 × 480"))])
    starter = forms.BooleanField(label=_("Start with event name, clock and a message"), required=False,
                                 initial=True)

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event

    def clean_size(self):
        return PRESETS[self.cleaned_data["size"]]

    def key(self) -> str:
        base = slugify(self.cleaned_data["name"])[:56] or "layout"
        key, n = base, 2
        while Layout.objects.filter(event=self.event, key=key).exists():
            key, n = f"{base}-{n}", n + 1
        return key


class LayoutMetaForm(forms.ModelForm):
    class Meta:
        model = Layout
        fields = ["name", "description", "theme"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["theme"].queryset = Theme.objects.filter(owner_q(event))
        self.fields["theme"].empty_label = _("The event's theme")


class PublishForm(forms.Form):
    at = forms.DateTimeField(label=_("Publish at"), required=False, widget=forms.DateTimeInput(
        attrs={"type": "datetime-local"}), help_text=_("Leave empty to publish now."))
