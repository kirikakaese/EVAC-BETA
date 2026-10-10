# EVAC - Event and Venue Administration Core
PY      := .venv/bin/python
PIP     := .venv/bin/pip
MANAGE  := $(PY) manage.py
COMPOSE := docker compose

DEPS_CMD = $(PY) -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb'))['project']; print('\n'.join(d['dependencies'] + d['optional-dependencies']['dev']))"

.PHONY: dev run worker beat channels test cov lint typecheck a11y migrate makemigrations seed openapi openapi-check frontend \
        attribution check e2e node-e2e load chaos up down logs shell build clean

dev:
	test -d .venv || python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(DEPS_CMD) | $(PIP) install -r /dev/stdin
	test -f .env || cp .env.example .env

run:
	$(MANAGE) runserver 0.0.0.0:8000

channels:
	.venv/bin/daphne -b 0.0.0.0 -p 8001 evac.asgi:application

worker:
	.venv/bin/celery -A evac worker -l info

beat:
	.venv/bin/celery -A evac beat -l info

test:
	$(PY) -m pytest -p no:cacheprovider

cov:
	$(PY) -m pytest -p no:cacheprovider --cov --cov-report=term --cov-report=xml
	$(PY) -m coverage report --include='apps/evacuation/*' --fail-under=95 --skip-covered

lint:
	.venv/bin/ruff check apps evac extensions bridge conftest.py scripts

typecheck:
	.venv/bin/mypy

a11y:
	$(MANAGE) evac_a11y

migrate:
	$(MANAGE) migrate --noinput

makemigrations:
	$(MANAGE) makemigrations

seed:
	$(MANAGE) evac_seed_demo

frontend:                                 # build static/player/ + static/editor/ from frontend/src (Node 22)
	cd frontend && npm ci --no-audit --no-fund && npm test && npm run build

openapi:
	DJANGO_SETTINGS_MODULE=evac.settings.test $(MANAGE) spectacular --file docs/api/openapi.yaml --validate

openapi-check:
	DJANGO_SETTINGS_MODULE=evac.settings.test $(MANAGE) spectacular --file /tmp/evac-openapi.yaml --validate
	diff -u docs/api/openapi.yaml /tmp/evac-openapi.yaml

attribution:
	$(PY) scripts/check_attribution.py

check: lint typecheck test openapi-check attribution
	SECRET_KEY=x EVAC_ALLOW_INSECURE=1 DATABASE_URL=sqlite:///build.sqlite3 $(MANAGE) check --settings=evac.settings.prod --deploy
	rm -f build.sqlite3

# Browser end-to-end tests (Phase 1 acceptance): throw-away server + demo data; needs `npm ci` and a Chromium
e2e:
	sh scripts/e2e.sh

# Central/node sync with two real instances (ADR-0036): enrol, checkout, alarms both ways, partition, check-in
node-e2e:
	$(PY) scripts/node_sync_e2e.py

# Placeholders until the evacuation module (Phase 3); see docs/ROADMAP.md
chaos load:
	@echo "'make $@' arrives with evacuation (phase 3) - see docs/ROADMAP.md"; exit 1

# --- Docker Compose ---------------------------------------------------------
up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f --tail=200

shell:
	$(COMPOSE) exec web python manage.py shell

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .ruff_cache .pytest_cache .mypy_cache .hypothesis staticfiles build.sqlite3 .coverage coverage.xml htmlcov
