# EVAC in GitHub Codespaces

Try EVAC in the browser without a server: on the repository page click **Code → Codespaces → Create
codespace on main** (or on any branch).

The first start takes a few minutes: it installs the dependencies, creates a SQLite database and fills it
with demo data (`.devcontainer/setup.sh`). Afterwards EVAC starts on port 8000 on every start of the
codespace (`.devcontainer/start.sh`) and the browser tab opens by itself. If it doesn't: **Ports** tab →
port 8000 → globe icon.

| Account | Password |
|---|---|
| `admin@evac.local` (instance admin) | `evac-demo-admin` |
| `orga@`, `control@`, `security@`, `helpdesk@`, `crew@`, `viewer@evac.local` | `evac-demo-admin` |

Admin roles need two-factor authentication for alarm-relevant actions: set it up under Account → Security
(an authenticator app or a passkey).

- The port is **private**: only you, logged in to GitHub, can open the link. Don't switch it to public.
- Server log: `tail -f /tmp/evac.log`. Restart: `pkill -f "manage.py runserver"; bash .devcontainer/start.sh`.
- Start over with fresh demo data: `rm evac.sqlite3 && bash .devcontainer/setup.sh`, then restart.
- E-mails (invitations) are not sent, they appear in the server log.
- No Redis, no Celery worker: background jobs run immediately, live updates use the in-memory channel layer.
- A stopped codespace keeps its data; GitHub stops it after 30 minutes without activity. Delete it under
  github.com/codespaces when you no longer need it.
