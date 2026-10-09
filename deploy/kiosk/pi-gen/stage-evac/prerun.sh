#!/bin/bash -e
# SPDX-License-Identifier: AGPL-3.0-or-later
# pi-gen: start this stage from the previous one (stage2 = Raspberry Pi OS Lite).
if [ ! -d "${ROOTFS_DIR}" ]; then
  copy_previous
fi
