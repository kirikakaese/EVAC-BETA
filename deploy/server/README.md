# Production server: EVAC + DIAL on one machine

Everything for running both management platforms on one fresh server (Debian 12 or Ubuntu 24.04,
16 GB RAM is plenty). Phone exchanges (Asterisk) run at the venues and connect to DIAL through the venue
agent, so the public server only opens SSH, HTTP and HTTPS.

```
Internet ──443──► Caddy (HTTPS, automatic Let's Encrypt certificates)
                    ├─ evac.pm → EVAC web 127.0.0.1:8100, /ws/ → EVAC channels 127.0.0.1:8101
                    └─ dial.pm → DIAL web 127.0.0.1:8200
/opt/evac   docker compose: web, channels, worker, beat, PostgreSQL, Redis
/opt/dial   docker compose: web, worker, beat, LDAP (localhost only), PostgreSQL, Redis
```

| File | Goes to |
|---|---|
| `bootstrap.sh` | run once as root: Docker, Caddy, firewall, automatic updates |
| `evac.override.yml` | `/opt/evac/docker-compose.override.yml` |
| `dial.override.yml` | `/opt/dial/docker-compose.override.yml` |
| `evac.env.production`, `dial.env.production` | values to put into each `.env` (besides the secrets) |
| `Caddyfile` | `/etc/caddy/Caddyfile` |
| `backup.sh`, `evac-dial-backup.service`, `evac-dial-backup.timer` | nightly backups |

Domains: **evac.pm** and **dial.pm**. Only `admin@example.org` in the `Caddyfile` still needs your
e-mail address (Let's Encrypt sends certificate expiry warnings there).

## 1. DNS

At your domain registrar, point both domains at the server: an **A record for `evac.pm`** and one for
**`dial.pm`** (the bare domain, `@`) with the server's IPv4 address, plus AAAA records if the server has
IPv6. Wait until `dig +short evac.pm` and `dig +short dial.pm` show the server IP - Caddy can only get
certificates after that.

## 2. Prepare the server (once)

Log in as root (or with sudo), make sure SSH works with your key, then:

```sh
apt-get update && apt-get install -y git
git clone https://github.com/kirikakaese/EVAC-BETA.git /opt/evac
git clone https://github.com/kirikakaese/DIAL-BETA.git /opt/dial
sh /opt/evac/deploy/server/bootstrap.sh
```

Both repositories are private: use a GitHub deploy key or a fine-grained read-only token for the clones.
`bootstrap.sh` installs Docker and Caddy, enables the firewall (22, 80, 443 only) and automatic security
updates. Then disable SSH password login: `PasswordAuthentication no` in `/etc/ssh/sshd_config`,
`systemctl reload ssh`.

## 3. EVAC

```sh
cd /opt/evac
cp .env.example .env
cp deploy/server/evac.override.yml docker-compose.override.yml
nano .env
```

In `.env`: set every value from `evac-secrets.env` and from `deploy/server/evac.env.production` (with your
domain) by **editing the existing line** of the same name - don't leave a key twice in the file. Then:

```sh
docker compose up -d --build
docker compose ps            # web, channels and worker become "healthy"
```

## 4. DIAL

```sh
cd /opt/dial
cp .env.example .env
cp /opt/evac/deploy/server/dial.override.yml docker-compose.override.yml
nano .env
```

In `.env`: set every value from `dial-secrets.env` and from `/opt/evac/deploy/server/dial.env.production`
by editing the existing lines (no duplicate keys). **`DIAL_SEED_DEMO=0` matters**: the default creates a demo
event with the account `admin@dial.local` / `admin`. Then:

```sh
docker compose up -d --build
docker compose exec web python manage.py createsuperuser   # your DIAL admin account
```

## 5. Caddy

```sh
cp /opt/evac/deploy/server/Caddyfile /etc/caddy/Caddyfile
nano /etc/caddy/Caddyfile          # your e-mail address in the first block
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Open `https://evac.pm`: the early-access page appears. Enter `EVAC_EARLY_ACCESS_PASSWORD`, then
the setup wizard asks for `EVAC_SETUP_TOKEN` and creates your admin account. Set up two-factor
authentication right after (Account → Security) - admin roles need it. `https://dial.pm` asks
for `DIAL_EARLY_ACCESS_PASSWORD`, then log in with the account from step 4.

## 6. Backups

```sh
cp /opt/evac/deploy/server/evac-dial-backup.service /opt/evac/deploy/server/evac-dial-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now evac-dial-backup.timer
systemctl start evac-dial-backup.service && ls -l /var/backups/evac-dial   # test run
```

Every night at about 03:15 both databases, media files and `.env` files (which contain the encryption
keys) are written to `/var/backups/evac-dial` (kept 14 days). **Copy them off the server** (restic, rsync
or your provider's backup space) - a backup on the same disk does not survive a disk failure. Restore a
database with `docker compose exec -T db pg_restore -U <user> -d <db> --clean < file.dump`.

## 7. Updates

```sh
cd /opt/evac && git pull && docker compose up -d --build   # migrations run automatically
cd /opt/dial && git pull && docker compose up -d --build
docker image prune -f
```

## Going public later

Remove `EVAC_EARLY_ACCESS_PASSWORD` / `DIAL_EARLY_ACCESS_PASSWORD` from the `.env` files and run
`docker compose up -d` in each folder.

## Running Asterisk on this server later

Only if phones should register directly on this server instead of at the venue: in
`/opt/dial/.env` set `DIAL_PBX_BACKEND=apps.pbx.backends.asterisk.AsteriskPBX` and `EXTERNAL_IP`, start it
with `docker compose --profile pbx up -d`, and open only SIP over TLS (`ufw allow 5061/tcp`) and the RTP
range (`ufw allow 10000:10200/udp`). Never expose ARI (8088) or AMI (5038): add
`ports: !override ["127.0.0.1:8088:8088", ...]` for the asterisk service in the override first, and add
fail2ban for SIP. Docker-published ports bypass ufw, so the override is what protects them.
