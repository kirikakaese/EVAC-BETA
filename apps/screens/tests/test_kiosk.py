# SPDX-License-Identifier: AGPL-3.0-or-later
"""The kiosk recipe in deploy/kiosk: scripts parse, carry the licence header and use the flags we rely on."""
import shutil
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

KIOSK = Path(settings.BASE_DIR) / "deploy" / "kiosk"
SCRIPTS = sorted(KIOSK.rglob("*.sh"))


def test_recipe_files_exist():
    names = {p.name for p in KIOSK.iterdir()}
    assert {"provision.sh", "evac-kiosk.sh", "evac-kiosk-watchdog.sh", "evac-kiosk.service",
            "evac-kiosk-watchdog.service", "evac-kiosk-watchdog.timer", "README.md"} <= names
    assert len(SCRIPTS) >= 5


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_scripts_parse_and_have_header(script):
    text = script.read_text()
    assert "SPDX-License-Identifier: AGPL-3.0-or-later" in text
    shell = "bash" if text.startswith("#!/bin/bash") else "sh"
    subprocess.run([shutil.which(shell) or shell, "-n", str(script)], check=True)


def test_kiosk_flags():
    text = (KIOSK / "evac-kiosk.sh").read_text()
    for flag in ("--kiosk", "--autoplay-policy=no-user-gesture-required", "--auto-accept-this-tab-capture",
                 "--remote-debugging-port=9222"):
        assert flag in text
    assert "127.0.0.1:9222" in (KIOSK / "evac-kiosk-watchdog.sh").read_text()


def test_provision_rejects_bad_usage():
    res = subprocess.run(["sh", str(KIOSK / "provision.sh"), "not-a-url"], capture_output=True, text=True)
    assert res.returncode == 2 and "usage" in res.stderr
