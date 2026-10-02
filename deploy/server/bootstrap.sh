#!/bin/sh
# One-time preparation of a fresh Debian 12 / Ubuntu 24.04 server for EVAC + DIAL.
# Run as root:  sh bootstrap.sh
# Installs Docker Engine (+ compose plugin) and Caddy from their official repositories, sets up ufw
# (SSH, HTTP, HTTPS only) and automatic security updates. Safe to run again.
set -eu

. /etc/os-release
apt-get update
apt-get install -y ca-certificates curl gnupg ufw unattended-upgrades git debian-keyring debian-archive-keyring \
  apt-transport-https

install -m 0755 -d /etc/apt/keyrings
# Docker
curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
# Caddy
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/caddy.gpg
echo "deb [signed-by=/etc/apt/keyrings/caddy.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" \
  > /etc/apt/sources.list.d/caddy.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin caddy

# Firewall: only SSH, HTTP (certificate challenges + redirect) and HTTPS
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Automatic security updates
dpkg-reconfigure -f noninteractive unattended-upgrades

mkdir -p /opt/evac /opt/dial /var/backups/evac-dial
echo "Done. Docker: $(docker --version); Compose: $(docker compose version --short); Caddy: $(caddy version)"
