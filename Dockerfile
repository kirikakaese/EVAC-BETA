# EVAC - Event and Venue Administration Core
# One image for every role; deploy/entrypoint.sh selects it: web | channels | worker | beat | <command>.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=evac.settings.prod

WORKDIR /app

# Runtime dependencies straight from pyproject.toml (layer-cached; the app runs from /app via manage.py).
COPY pyproject.toml ./
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb'))['project']; print('\n'.join(d['dependencies']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY . /app

RUN SECRET_KEY=build EVAC_ALLOW_INSECURE=1 DATABASE_URL=sqlite:///build.sqlite3 \
    python manage.py collectstatic --noinput \
    && rm -f build.sqlite3

RUN groupadd --system evac && useradd --system --gid evac --home-dir /app --shell /usr/sbin/nologin evac \
    && mkdir -p /app/media \
    && chmod +x /app/deploy/entrypoint.sh \
    && chown -R evac:evac /app

USER evac
EXPOSE 8000 8001
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["web"]
