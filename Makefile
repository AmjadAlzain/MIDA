# MIDA Project Makefile
# Common commands for development and deployment

.PHONY: help install run test lint format clean db-setup db-revision db-up db-down \
        docker-build docker-up docker-down docker-logs docker-migrate docker-backup \
        docker-restore docker-monitor setup

# Default target
help:
	@echo "MIDA Project - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install      - Install Python dependencies"
	@echo "  make run          - Run the FastAPI server (development)"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linting (ruff)"
	@echo "  make format       - Format code (ruff)"
	@echo "  make clean        - Remove cache files"
	@echo ""
	@echo "Database (local):"
	@echo "  make db-revision  - Create new Alembic migration (MSG=...)"
	@echo "  make db-up        - Run migrations (alembic upgrade head)"
	@echo "  make db-down      - Rollback one migration (alembic downgrade -1)"
	@echo ""
	@echo "Docker/Production:"
	@echo "  make setup        - Run interactive setup wizard"
	@echo "  make docker-build - Build Docker images"
	@echo "  make docker-up    - Start all services"
	@echo "  make docker-down  - Stop all services"
	@echo "  make docker-logs  - View live logs"
	@echo "  make docker-migrate - Run database migrations"
	@echo "  make docker-backup  - Create database backup"
	@echo "  make docker-restore - Restore from backup (FILE=...)"
	@echo "  make docker-monitor - Check service health"
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

# =============================================================================
# Docker/Production Commands
# =============================================================================

# Run interactive setup wizard
setup:
	bash scripts/setup.sh

# Build Docker images
docker-build:
	docker compose build

# Start all services (detached)
docker-up:
	docker compose up -d mida-api mida-frontend db-backup
	@echo "Services starting... checking health in 10s"
	@sleep 10
	docker compose ps

# Stop all services
docker-down:
	docker compose down

# View live logs (all services)
docker-logs:
	docker compose logs -f

# View API logs only
docker-logs-api:
	docker compose logs -f mida-api

# Run database migrations
docker-migrate:
	docker compose run --rm db-migrate

# Create database backup
docker-backup:
	bash scripts/backup.sh

# Restore database from backup
# Usage: make docker-restore FILE=./backups/mida_backup_20240101_120000.sql.gz
docker-restore:
	bash scripts/restore.sh $(FILE)

# Check service health
docker-monitor:
	bash scripts/monitor.sh

# Full deployment (build + migrate + start)
docker-deploy: docker-build docker-migrate docker-up
	@echo "Deployment complete!"

# Restart services
docker-restart:
	docker compose restart mida-api mida-frontend

# View container resource usage
docker-stats:
	docker stats mida-ocr-api mida-frontend mida-postgres
