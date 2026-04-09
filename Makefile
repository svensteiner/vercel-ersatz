# Ersatz Makefile

.PHONY: install dev build up down logs clean test lint

# Installation
install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"

# Docker
build:
	docker compose build

up:
	docker compose up -d

up-dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

down:
	docker compose down

logs:
	docker compose logs -f

# Development
dev:
	uvicorn deploy-server.main:app --reload --host 0.0.0.0 --port 9000

# Testing
test:
	pytest tests/ -v --cov=.

test-cov:
	pytest tests/ -v --cov=. --cov-report=html

# Linting
lint:
	ruff check .
	mypy .

format:
	ruff format .

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache

# CLI
cli-install:
	pip install -e .
	@echo "Ersatz CLI installed. Run 'ersatz --help' to get started."
