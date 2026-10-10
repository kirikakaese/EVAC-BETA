# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class ProgramImportConfig(AppConfig):
    name = "extensions.program_import"
    label = "program_import"
    verbose_name = "Program import (pretalx, frab, iCal)"
