# Developer entry point. `make help` lists targets.
SHELL := /bin/bash
PY := .venv/bin/python
DJANGO := $(PY) manage.py
UV := uv

.DEFAULT_GOAL := help
.PHONY: help sync up down ps migrate makemigrations run worker beat mcp test lint fmt eval \
        hermes-build hermes-spike tailwind-build seed-demo

help:
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z0-9_.-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

sync: ## Install dependencies into .venv from uv.lock.
	$(UV) sync --group dev

up: ## Start postgres and redis.
	docker compose up -d postgres redis

down: ## Stop containers.
	docker compose down

ps: ## List containers.
	docker compose ps

# Migrations and tests run as kb_migrator (owns the schema, CREATEDB); runtime as kb_app.
MIGRATOR_URL = $$(grep -E '^MIGRATOR_DATABASE_URL=' .env | cut -d= -f2-)

migrate: ## Apply migrations as the migrator role (MIGRATOR_DATABASE_URL in .env).
	DATABASE_URL=$(MIGRATOR_URL) $(DJANGO) migrate

makemigrations: ## Create migrations for model changes.
	$(DJANGO) makemigrations

run: ## Development server on :8000.
	$(DJANGO) runserver

worker: ## Celery worker.
	.venv/bin/celery -A knowledgebase worker -l INFO

beat: ## Celery beat (static schedule from settings).
	.venv/bin/celery -A knowledgebase beat -l INFO

mcp: ## Knowledge MCP server on :8710.
	$(DJANGO) run_mcp_server --host 127.0.0.1 --port 8710

test: ## Full test suite against the compose Postgres, as the migrator role.
	DATABASE_URL=$(MIGRATOR_URL) $(PY) -m pytest -q

lint: ## Ruff check.
	$(PY) -m ruff check .

fmt: ## Ruff format and autofix.
	$(PY) -m ruff format . && $(PY) -m ruff check --fix .

eval: ## Retrieval and grounding evaluation on the synthetic corpus.
	$(DJANGO) run_eval

tailwind-build: ## Build the Tailwind CSS bundle.
	$(DJANGO) tailwind build

hermes-build: ## Build the hermes-agent image (pinned Hermes tag plus the runner).
	docker compose --profile hermes build hermes-agent

hermes-spike: ## Run the Hermes CLI contract checks inside the image; results go to HERMES_INTEGRATION.md.
	docker compose --profile hermes run --rm hermes-agent python3 /opt/runner/spike.py

seed-demo: ## Create a demo organization, users and synthetic documents.
	$(DJANGO) seed_demo
