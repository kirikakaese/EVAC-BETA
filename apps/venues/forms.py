# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms

from .models import Building, Edge, Floor, Point, Room, Zone


class BuildingForm(forms.ModelForm):
    class Meta:
        model = Building
        fields = ["name", "outdoor", "order"]


class FloorForm(forms.ModelForm):
    class Meta:
        model = Floor
        fields = ["building", "name", "level"]

    def __init__(self, *args, venue, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["building"].queryset = venue.buildings.all()


class ZoneForm(forms.ModelForm):
    class Meta:
        model = Zone
        fields = ["name", "outdoor", "capacity", "color"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["name", "floor", "zones", "capacity", "step_free", "has_lift", "wheelchair_spaces"]
        widgets = {"zones": forms.CheckboxSelectMultiple}

    def __init__(self, *args, venue, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["floor"].queryset = Floor.objects.filter(building__venue=venue).select_related("building")
        self.fields["zones"].queryset = venue.zones.all()


class PointForm(forms.ModelForm):
    class Meta:
        model = Point
        fields = ["kind", "name", "floor", "zone", "room", "x", "y", "capacity", "step_free", "note"]

    def __init__(self, *args, venue, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["floor"].queryset = Floor.objects.filter(building__venue=venue).select_related("building")
        self.fields["zone"].queryset = venue.zones.all()
        self.fields["room"].queryset = venue.rooms.all()


class EdgeForm(forms.ModelForm):
    class Meta:
        model = Edge
        fields = ["a", "b", "one_way", "length_m", "step_free"]

    def __init__(self, *args, venue, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("a", "b"):
            self.fields[name].queryset = venue.points.all()

    def clean(self):
        cleaned = super().clean()
        a, b = cleaned.get("a"), cleaned.get("b")
        if a and b and a == b:
            raise forms.ValidationError("A connection needs two different points.")
        if a and b and Edge.objects.filter(a=b, b=a).exists():
            raise forms.ValidationError("These points are already connected.")
        return cleaned
