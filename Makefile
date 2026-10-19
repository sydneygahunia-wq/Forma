# Common tasks. Run `make help` for the list.
.PHONY: help setup backend frontend test test-backend test-frontend e2e lint bench load up down

PY := backend/.venv/bin/python

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup: ## Create the Python venv and install all dependencies
	python3.12 -m venv backend/.venv
	$(PY) -m pip install -r backend/requirements-dev.txt
	cd frontend && npm install

backend: ## Run the API + embedded simulation on :8000 (SQLite)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend: ## Run the Next.js dev server on :3000
	cd frontend && npm run dev

test: test-backend test-frontend ## Run all unit/integration tests

test-backend:
	cd backend && .venv/bin/python -m pytest -q

test-frontend:
	cd frontend && npm test

e2e: ## Playwright end-to-end tests (boots its own servers)
	cd frontend && npx playwright test

lint: ## Lint + type-check everything
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app
	cd frontend && npm run lint && npm run typecheck

bench: ## Regenerate docs/BENCHMARKS.md
	cd backend && .venv/bin/python scripts/benchmark.py --out ../docs/BENCHMARKS.md

load: ## Load-test a running API (make backend first)
	cd backend && .venv/bin/python scripts/load_test.py --orders 300 --concurrency 30

up: ## Full stack in Docker: Postgres, Redis, API, worker, web
	docker compose up --build

down:
	docker compose down
