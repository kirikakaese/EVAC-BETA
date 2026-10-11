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
- **Blank page or nothing on port 8000?** Run `bash .devcontainer/start.sh` in the terminal. It installs new
  dependencies after a `git pull`, migrates the database, (re)starts EVAC and waits until it answers; if it does
  not, it prints the end of the log.
- **Screens (`/player/`) say "EVAC server not reachable"**: the player calls the API without cookies (a screen
  authenticates with its own token), and a private codespace port turns away requests without GitHub's login
  cookie. Open the player through a forwarded port instead: on your own computer run
  `gh codespace ports forward 8000:8000` (GitHub CLI) and open `http://localhost:8000/player/`, or open the
  codespace in VS Code Desktop, which forwards the port to `localhost` by itself. Pair it from the browser tab you
  are logged in with (*Screens → Pair*). Layout previews in the portal work without this.
- Server log: `tail -f /tmp/evac.log`. Restart: `bash .devcontainer/start.sh`.
- Start over with fresh demo data: `rm evac.sqlite3 && bash .devcontainer/setup.sh`, then restart.
- E-mails (invitations) are not sent, they appear in the server log.
- No Redis, no Celery worker: background jobs run immediately, live updates use the in-memory channel layer.
- A stopped codespace keeps its data; GitHub stops it after 30 minutes without activity. Delete it under
  github.com/codespaces when you no longer need it.
