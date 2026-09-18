.DEFAULT_GOAL := help
.PHONY: help setup dev backend frontend test docker clean

PY := backend/venv/bin/python

help: ## Show this help
	@echo "Blundr"
	@echo
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  No local toolchain? Use 'docker compose up' instead."

setup: ## Check tooling, then install backend and frontend dependencies
	@./scripts/preflight.sh
	@test -d backend/venv || python3 -m venv backend/venv
	@$(PY) -m pip install --quiet --upgrade pip
	@$(PY) -m pip install --quiet -r backend/requirements-dev.txt
	@cd frontend && npm install --silent
	@test -f .env || cp .env.example .env
	@echo "Dependencies installed. Run 'make dev'."

dev: ## Run backend and frontend together (ctrl-c stops both)
	@echo "backend  -> http://localhost:8000"
	@echo "frontend -> http://localhost:5173"
	@set -m; \
		trap 'kill -TERM -$$BACK -$$FRONT 2>/dev/null' INT TERM EXIT; \
		( cd backend && exec ./venv/bin/uvicorn app.main:app --reload --port 8000 ) & BACK=$$!; \
		( cd frontend && exec ./node_modules/.bin/vite ) & FRONT=$$!; \
		wait

backend: ## Run only the backend
	@cd backend && ./venv/bin/uvicorn app.main:app --reload --port 8000

frontend: ## Run only the frontend
	@cd frontend && npm run dev

test: ## Run the backend test suite
	@cd backend && ./venv/bin/python -m pytest

docker: ## Build and run everything in containers
	@docker compose up --build

clean: ## Remove the venv, node_modules and build output
	@rm -rf backend/venv frontend/node_modules frontend/dist
	@find backend -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "Cleaned. Run 'make setup' to start over."
