# MIDA Project Makefile
# Common commands for development and deployment

.PHONY: help install run test lint format clean db-setup db-revision db-up db-down \
        docker-build docker-up docker-down docker-logs docker-clean docker-dev \
        frontend-install frontend-dev frontend-build

# Default target
help:
	@echo "MIDA Project - Available commands:"
	@echo ""
	@echo "  Development:"
	@echo "    make install        - Install Python dependencies"
	@echo "    make run            - Run the FastAPI server (development)"
	@echo "    make frontend-dev   - Run frontend dev server"
	@echo "    make test           - Run tests"
	@echo "    make lint           - Run linting (ruff)"
	@echo "    make format         - Format code (ruff)"
	@echo ""
	@echo "  Database:"
	@echo "    make db-setup       - Run legacy database setup script"
	@echo "    make db-revision    - Create new Alembic migration (MSG=...)"
	@echo "    make db-up          - Run migrations (alembic upgrade head)"
	@echo "    make db-down        - Rollback one migration (alembic downgrade -1)"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker-build   - Build all Docker images"
	@echo "    make docker-up      - Start all containers (production)"
	@echo "    make docker-dev     - Start all containers (development)"
	@echo "    make docker-down    - Stop all containers"
	@echo "    make docker-logs    - View container logs"
	@echo "    make docker-clean   - Remove containers, images, and volumes"
	@echo ""
	@echo "  Other:"
	@echo "    make clean          - Remove cache files"
	@echo ""

# Install dependencies
install:
	cd server && pip install -r requirements.txt

# Run the FastAPI server in development mode
run:
	cd server && uvicorn app.main:app --reload --port 8000

# Run the FastAPI server in production mode
run-prod:
	cd server && uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run tests
test:
	cd server && python -m pytest -v

# Run linting
lint:
	cd server && python -m ruff check .

# Format code
format:
	cd server && python -m ruff format .

# Legacy database setup (tools/db_setup)
db-setup:
	cd server/tools/db_setup && python Kagayaku_db.py

# Create new Alembic migration with autogenerate
# Usage: make db-revision MSG="add users table"
db-revision:
	cd server && alembic revision --autogenerate -m "$(MSG)"

# Run all pending migrations
db-up:
	cd server && alembic upgrade head

# Rollback one migration
db-down:
	cd server && alembic downgrade -1

# Clean cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# ==========================================
# Frontend Commands
# ==========================================

# Install frontend dependencies
frontend-install:
	cd frontend && npm ci

# Run frontend dev server
frontend-dev:
	cd frontend && npm run dev

# Build frontend for production
frontend-build:
	cd frontend && npm run build

# ==========================================
# Docker Commands
# ==========================================

# Build all Docker images
docker-build:
	docker-compose build

# Start all containers (production)
docker-up:
	docker-compose up -d

# Start all containers (development with hot reload)
docker-dev:
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Stop all containers
docker-down:
	docker-compose down

# View container logs
docker-logs:
	docker-compose logs -f

# View specific service logs
docker-logs-api:
	docker-compose logs -f mida-api

docker-logs-frontend:
	docker-compose logs -f mida-frontend

docker-logs-db:
	docker-compose logs -f postgres

# Rebuild and restart a specific service
docker-restart-api:
	docker-compose up -d --build mida-api

docker-restart-frontend:
	docker-compose up -d --build mida-frontend

# Run migrations in Docker
docker-migrate:
	docker-compose run --rm migrations

# Remove containers, images, and volumes
docker-clean:
	docker-compose down -v --rmi local

# Full clean and rebuild
docker-rebuild:
	docker-compose down -v --rmi local
	docker-compose build --no-cache
	docker-compose up -d
