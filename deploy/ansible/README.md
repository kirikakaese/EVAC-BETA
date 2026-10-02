# Ansible role `evac`

Installs EVAC from this repository on a Debian/Ubuntu host with systemd: system packages, a virtualenv
in `/opt/evac`, `/etc/evac/evac.env`, migrations, static files and the systemd units from
`deploy/systemd/`. PostgreSQL and Redis are expected to exist (local or remote); put a TLS reverse proxy
(Caddy, nginx) in front and route `/ws/` to `127.0.0.1:8001`, everything else to `127.0.0.1:8000`.

```yaml
# playbook.yml
- hosts: evac
  become: true
  roles:
    - role: evac
      vars:
        evac_version: main
        evac_env:
          SECRET_KEY: "{{ vault_evac_secret_key }}"
          EVAC_SECRETS_KEYS: "{{ vault_evac_secrets_keys }}"
          DATABASE_URL: postgres://evac:{{ vault_db_password }}@localhost:5432/evac
          REDIS_URL: redis://localhost:6379/0
          EVAC_PUBLIC_URL: https://evac.example.org
          ALLOWED_HOSTS: evac.example.org
          CSRF_TRUSTED_ORIGINS: https://evac.example.org
```

The same role installs a venue node: add `EVAC_MODE: node` to `evac_env` (see
`docs/OPERATOR_HANDBOOK.md`, "Venue node").
