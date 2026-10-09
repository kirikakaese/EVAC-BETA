# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in open-licence fonts (static files in static/fonts/, SIL Open Font License 1.1)."""
import uuid
from pathlib import Path

from django.conf import settings
from django.db import migrations

ATKINSON = uuid.UUID("6f0d8d3e-7c1a-4f5b-9a40-0a7e4a0c0001")
INTER = uuid.UUID("6f0d8d3e-7c1a-4f5b-9a40-0a7e4a0c0002")
LATIN = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,"
         "U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD")


def _size(rel: str) -> int:
    p = Path(settings.BASE_DIR) / "static" / rel
    return p.stat().st_size if p.exists() else 0


def add(apps, schema_editor):
    Family = apps.get_model("content", "FontFamily")
    File = apps.get_model("content", "FontFile")
    atk = Family.objects.create(
        id=ATKINSON, name="Atkinson Hyperlegible", category="sans", builtin=True,
        licence="Braille Institute, SIL Open Font License 1.1 (static/fonts/atkinson-hyperlegible/OFL.txt). "
                "Designed for legibility; recommended for evacuation and wayfinding screens.")
    for weight in (400, 700):
        for style in ("normal", "italic"):
            rel = f"fonts/atkinson-hyperlegible/atkinson-hyperlegible-latin-{weight}-{style}.woff2"
            File.objects.create(family=atk, static_path=rel, weight_min=weight, weight_max=weight, style=style,
                                unicode_range=LATIN, original_format="woff2", size=_size(rel))
    inter = Family.objects.create(
        id=INTER, name="Inter", category="sans", builtin=True,
        licence="Rasmus Andersson, SIL Open Font License 1.1 (static/fonts/inter/OFL.txt). Variable weight 100-900.")
    for style in ("normal", "italic"):
        rel = f"fonts/inter/inter-latin-wght-{style}.woff2"
        File.objects.create(family=inter, static_path=rel, weight_min=100, weight_max=900, style=style,
                            unicode_range=LATIN, original_format="woff2", size=_size(rel),
                            axes=[{"tag": "wght", "min": 100, "max": 900, "default": 400, "name": "Weight"}])


def remove(apps, schema_editor):
    apps.get_model("content", "FontFamily").objects.filter(id__in=[ATKINSON, INTER]).delete()


class Migration(migrations.Migration):
    dependencies = [("content", "0001_initial")]
    operations = [migrations.RunPython(add, remove)]
