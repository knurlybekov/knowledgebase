# Application image for web, worker, beat and knowledge-mcp.
# One stage: psycopg[binary] bundles libpq and uv installs from the lock file.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=knowledgebase.settings

COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# Tailwind build needs the standalone binary (downloaded once at build time) and
# collectstatic needs settings; build-only values stand in for runtime secrets.
RUN SECRET_KEY=build-only DATABASE_URL=postgres://x:x@localhost/x CONNECTOR_TOKEN_KEY=build-only \
    python manage.py tailwind build \
 && SECRET_KEY=build-only DATABASE_URL=postgres://x:x@localhost/x CONNECTOR_TOKEN_KEY=build-only \
    python manage.py collectstatic --noinput

RUN useradd --create-home --uid 10001 kb && chown -R kb:kb /app/staticfiles
USER kb

EXPOSE 8000
ENTRYPOINT ["sh", "/app/scripts/docker-entrypoint.sh"]
CMD ["gunicorn", "knowledgebase.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
