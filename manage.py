#!/usr/bin/env python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Django's command-line utility for EVAC."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evac.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
