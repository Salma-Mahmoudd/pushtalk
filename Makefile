# Shortcuts for common tasks. Run `make` or `make help` to list them.
COMPOSE     := docker compose
COMPOSE_DEV := docker compose -f docker-compose.yml -f docker-compose.dev.yml
PLANTUML    := plantuml/plantuml:1.2025.4

.DEFAULT_GOAL := help
.PHONY: help up down reset logs ps dev services migrate migration test test-api test-web lint diagrams

help: ## List the available commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

up: ## Build and start the whole app on http://localhost:8080
	$(COMPOSE) up --build -d
	@echo "PushTalk: http://localhost:$${WEB_PORT:-8080}"

down: ## Stop the app (data is kept)
	$(COMPOSE_DEV) down

reset: ## Stop the app and delete all data (database, Redis)
	$(COMPOSE_DEV) down -v

logs: ## Follow the app logs
	$(COMPOSE) logs -f

ps: ## Show service status
	$(COMPOSE) ps

dev: ## Start everything with the API on :8001 (hot reload) and PostgreSQL/Redis published
	$(COMPOSE_DEV) up --build -d

services: ## Start only PostgreSQL and Redis (published) for running the API and tests locally
	$(COMPOSE_DEV) up -d postgres redis

migrate: ## Apply database migrations (services must be running)
	cd apps/api && uv run alembic upgrade head

migration: ## Create a migration from model changes: make migration m="add users"
	cd apps/api && uv run alembic revision --autogenerate -m "$(m)"

test: test-api test-web ## Run all tests

test-api: ## API tests (integration tests need `make services`)
	cd apps/api && uv run pytest

test-web: ## Web checks: type check and build
	cd apps/web && pnpm build

lint: ## Lint and type-check both apps
	cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd apps/web && pnpm lint

diagrams: ## Re-render specs/ diagrams to SVG (Docker, no Java needed)
	docker run --rm --user "$$(id -u):$$(id -g)" -e JAVA_TOOL_OPTIONS=-Duser.home=/tmp \
		-v "$(CURDIR)":/work -w /work $(PLANTUML) -tsvg specs/*/*.puml
