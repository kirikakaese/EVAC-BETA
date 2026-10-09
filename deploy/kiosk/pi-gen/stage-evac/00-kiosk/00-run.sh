#!/bin/bash -e
# SPDX-License-Identifier: AGPL-3.0-or-later
# pi-gen: copy the kiosk recipe into the image and run it there (services are enabled, not started).
# EVAC_URL comes from the pi-gen config file (see deploy/kiosk/README.md).
install -d "${ROOTFS_DIR}/opt/evac-kiosk"
cp "${STAGE_DIR}/../../"*.sh "${STAGE_DIR}/../../"*.service "${STAGE_DIR}/../../"*.timer "${ROOTFS_DIR}/opt/evac-kiosk/"
on_chroot << CHROOT
sh /opt/evac-kiosk/provision.sh "${EVAC_URL:?set EVAC_URL in the pi-gen config}" --image
CHROOT
