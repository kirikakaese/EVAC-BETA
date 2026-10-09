# EVAC - Event and Venue Administration Core
PY      := .venv/bin/python
PIP     := .venv/bin/pip
MANAGE  := $(PY) manage.py
COMPOSE := docker compose

DEPS_CMD = $(PY) -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb'))['project']; print('\n'.join(d['dependencies'] + d['optional-dependencies']['dev']))"

.PHONY: dev run worker beat channels test cov lint typecheck a11y migrate makemigrations seed openapi openapi-check player \
        attribution check e2e load chaos up down logs shell build clean

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

lint:
	.venv/bin/ruff check apps evac extensions conftest.py scripts

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

player:                                   # build static/player/ from player/src (needs Node 22)
	cd player && npm ci --no-audit --no-fund && npm test && npm run build

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

# Placeholders until the screen player exists (Phase 1) and the evacuation module (Phase 3); see docs/ROADMAP.md
e2e load chaos:
	@echo "'make $@' arrives with the player (phase 1) and evacuation (phase 3) - see docs/ROADMAP.md"; exit 1

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
