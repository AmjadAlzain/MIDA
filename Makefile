# MIDA Project Makefile
# Common commands for development

.PHONY: help install run test lint format clean db-setup db-revision db-up db-down

# Default target
help:
	@echo "MIDA Project - Available commands:"
	@echo ""
	@echo "  make install      - Install Python dependencies"
	@echo "  make run          - Run the FastAPI server (development)"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linting (ruff)"
	@echo "  make format       - Format code (ruff)"
	@echo "  make db-setup     - Run legacy database setup script"
	@echo "  make db-revision  - Create new Alembic migration (MSG=...)"
	@echo "  make db-up        - Run migrations (alembic upgrade head)"
	@echo "  make db-down      - Rollback one migration (alembic downgrade -1)"
	@echo "  make clean        - Remove cache files"
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
