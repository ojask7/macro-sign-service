.PHONY: help install dev run test lint format docker-up docker-down clean migrate generate-cert

# Variables
PYTHON := python3
PIP := pip
UVICORN := uvicorn
CELERY := celery
DOCKER_COMPOSE := docker-compose

# Colors
GREEN  := \033[0;32m
YELLOW := \033[0;33m
CYAN   := \033[0;36m
RESET  := \033[0m

help: ## Show this help message
	@echo "$(CYAN)Macro Sign Service$(RESET) - Available commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

# ============================================================================
# Development
# ============================================================================

install: ## Install all dependencies
	$(PIP) install -r requirements.txt

dev: ## Run development server with auto-reload
	$(UVICORN) src.main:app --reload --host 0.0.0.0 --port 8000

run: ## Run production server
	$(UVICORN) src.main:app --host 0.0.0.0 --port 8000 --workers 4

worker: ## Start Celery worker
	$(CELERY) -A src.queue.celery_app:celery_app worker --loglevel=info -Q signing,verification,webhooks,default

worker-beat: ## Start Celery beat scheduler
	$(CELERY) -A src.queue.celery_app:celery_app beat --loglevel=info

# ============================================================================
# Testing
# ============================================================================

test: ## Run all tests
	$(PYTHON) -m pytest tests/ -v --cov=src --cov-report=term-missing

test-unit: ## Run unit tests only
	$(PYTHON) -m pytest tests/unit/ -v --cov=src --cov-report=term-missing

test-integration: ## Run integration tests only
	$(PYTHON) -m pytest tests/integration/ -v

test-e2e: ## Run end-to-end tests
	$(PYTHON) -m pytest tests/e2e/ -v

test-coverage: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ --cov=src --cov-report=html --cov-report=xml
	@echo "$(GREEN)Coverage report: htmlcov/index.html$(RESET)"

# ============================================================================
# Code Quality
# ============================================================================

lint: ## Run linters
	ruff check src/ tests/
	black --check src/ tests/
	mypy src/ --ignore-missing-imports

format: ## Format code
	black src/ tests/
	ruff check --fix src/ tests/

# ============================================================================
# Database
# ============================================================================

migrate: ## Run database migrations
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="description")
	alembic revision --autogenerate -m "$(MSG)"

migrate-rollback: ## Rollback last migration
	alembic downgrade -1

# ============================================================================
# Docker
# ============================================================================

docker-up: ## Start all services with Docker Compose
	$(DOCKER_COMPOSE) up -d

docker-down: ## Stop all Docker Compose services
	$(DOCKER_COMPOSE) down

docker-build: ## Build Docker images
	$(DOCKER_COMPOSE) build

docker-logs: ## View Docker Compose logs
	$(DOCKER_COMPOSE) logs -f

docker-restart: ## Restart all services
	$(DOCKER_COMPOSE) restart

# ============================================================================
# CLI & Certificates
# ============================================================================

generate-cert: ## Generate a self-signed development certificate
	$(PYTHON) -m cli generate-cert --name "Dev Certificate" --days 365

sign-local: ## Sign a file locally (usage: make sign-local FILE=path/to/file.vba)
	$(PYTHON) -m cli sign --local $(FILE)

# ============================================================================
# Cleanup
# ============================================================================

clean: ## Clean generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf .mypy_cache dist build *.egg-info

clean-all: clean ## Clean everything including certs and Docker volumes
	rm -rf certs/
	$(DOCKER_COMPOSE) down -v
