# Kagayaku Import System (KIS)

A comprehensive system for managing MIDA (Malaysian Investment Development Authority) import duty exemption certificates with automated OCR parsing, invoice classification, K1 export generation, and quota tracking.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Frontend Pages](#frontend-pages)
- [Database](#database)
- [Deployment](#deployment)
- [Development](#development)
- [License](#license)

---

## Features

| Feature | Description |
|---------|-------------|
| **Certificate OCR Parsing** | Upload MIDA certificate PDFs — Azure Document Intelligence extracts certificate data, items, and station-split quantities |
| **3-Tab Invoice Classification** | Classify invoice items into Form-D, MIDA, and Duties Payable categories with company-specific SST rules |
| **K1 XLS Export** | Export classified items to K1 Import format with proper duty/SST exemption settings |
| **Multi-Certificate Matching** | Match invoice items against multiple MIDA certificates simultaneously via HS code + description fuzzy matching |
| **Import Quota Tracking** | Track import history per certificate item with automatic balance recalculation per port |
| **Balance Sheet Migration** | Upload historical XLSX balance sheets to migrate existing import records |
| **Balance Sheet Export** | Generate MIDA-template-format XLSX balance sheets per port |
| **Certificate Editor** | Insert rows, mark dummy entries, inline edit certificate items |

---

## Architecture

```
+---------------------+     +---------------------+     +--------------+
|   React Frontend    |---->|   FastAPI Backend    |---->|  PostgreSQL  |
|   (Vite + TS)       | /api|   (Python 3.10+)    |     |  Database    |
+---------------------+     +----------+----------+     +--------------+
                                       |
                                       v
                            +---------------------+
                            |  Azure Document      |
                            |  Intelligence (OCR)  |
                            +---------------------+
```

- **Frontend**: React 18 + TypeScript, Vite, Tailwind CSS, React Query
- **Backend**: FastAPI with async support, SQLAlchemy ORM, Alembic migrations
- **Database**: PostgreSQL 15 with port-specific quota tracking
- **OCR**: Azure Document Intelligence for PDF certificate parsing
- **Deployment**: Docker Compose with Nginx reverse proxy

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ (or Docker)
- Azure Document Intelligence account

### Option 1: Docker (Recommended)

```bash
# Configure environment
cp .env.example .env
# Edit .env with your Azure credentials and database password

# Build and start all services
docker compose build
docker compose up -d postgres
sleep 15
docker compose run --rm db-migrate
docker compose up -d kis-api kis-frontend db-backup

# Verify
docker compose ps
curl http://localhost:8000/health
```

Access the application at:
- **Frontend**: http://localhost
- **API Docs**: http://localhost:8000/docs

### Option 2: Local Development

```bash
# Backend
cd server
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
cp ../.env.example .env        # Edit with your credentials
uvicorn app.main:app --reload --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

Frontend at http://localhost:3000 (proxies `/api` to backend).

### Option 3: Makefile

```bash
make install     # Install Python dependencies
make run         # Run backend in dev mode
make test        # Run tests
make lint        # Lint code
```

---

## Project Structure

```
KIS/
+-- frontend/                      # React TypeScript SPA
|   +-- src/
|   |   +-- components/            # Layout, UI components
|   |   +-- pages/                 # Route-level page components
|   |   +-- services/              # API service layer (Axios)
|   |   +-- types/                 # TypeScript interfaces
|   |   +-- utils/                 # Utility functions
|   +-- nginx.conf                 # Production Nginx config
|   +-- Dockerfile                 # Multi-stage build
|   +-- package.json
+-- server/                        # FastAPI backend
|   +-- app/
|   |   +-- main.py                # App entry point, middleware
|   |   +-- config.py              # Environment-based settings
|   |   +-- clients/               # External API clients
|   |   +-- db/                    # Database engine, session, mixins
|   |   +-- models/                # SQLAlchemy ORM models
|   |   +-- repositories/          # Data access layer
|   |   +-- routers/               # API endpoint handlers
|   |   +-- schemas/               # Pydantic request/response schemas
|   |   +-- services/              # Business logic layer
|   +-- alembic/                   # Database migrations (11 versions)
|   +-- templates/                 # K1 export XLS template
|   +-- tests/                     # Unit and integration tests
|   +-- Dockerfile
|   +-- requirements.txt
+-- scripts/                       # Deployment & utility scripts
+-- docker-compose.yml             # Production orchestration
+-- Makefile                       # Development shortcuts
+-- .env.example                   # Environment template
+-- DEPLOYMENT.md                  # Deployment guide
+-- QUICK_DEPLOY.md                # Quick deployment steps
+-- DOCUMENTATION.md               # Technical documentation
```

---

## Configuration

All configuration uses environment variables (12-factor app). Copy `.env.example` to `.env` and edit.

### Required

| Variable | Description |
|----------|-------------|
| `AZURE_DI_ENDPOINT` | Azure Document Intelligence endpoint URL |
| `AZURE_DI_KEY` | Azure Document Intelligence API key |
| `POSTGRES_PASSWORD` | PostgreSQL password |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Auto-generated | PostgreSQL connection string |
| `ENVIRONMENT` | `development` | `development`, `staging`, `production` |
| `DEBUG` | `false` | Enable debug mode |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `ALLOWED_NETWORKS` | *(empty)* | Comma-separated CIDR ranges for IP whitelisting |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `json` | `json` (production) or `text` (development) |
| `WORKERS` | `4` | Number of API workers |
| `API_PORT` | `8000` | Backend port |
| `FRONTEND_PORT` | `80` | Frontend port |
| `BACKUP_RETENTION_DAYS` | `7` | Days to keep database backups |

---

## API Reference

Interactive API documentation is available at `/docs` (Swagger UI) when the server is running.

### Conversion & Classification

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/companies` | List companies for classification |
| `POST` | `/api/convert/classify` | 3-tab invoice classification |
| `POST` | `/api/convert/export-classified` | Export items to K1 XLS |
| `POST` | `/api/convert` | Single-certificate MIDA matching |
| `POST` | `/api/convert-multi` | Multi-certificate MIDA matching |

### Certificate Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/mida/certificates/` | List certificates (paginated) |
| `GET` | `/api/mida/certificates/{id}` | Get certificate with items |
| `POST` | `/api/mida/certificates/draft` | Create/update draft |
| `PUT` | `/api/mida/certificates/{id}` | Update draft |
| `POST` | `/api/mida/certificates/{id}/confirm` | Confirm (lock) certificate |
| `DELETE` | `/api/mida/certificates/{id}` | Soft-delete certificate |

### Certificate Parsing (OCR)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/mida/certificate/parse` | Parse certificate PDF via OCR |
| `POST` | `/api/mida/certificate/parse-debug` | Parse with debug statistics |

### Import Tracking

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/mida/imports` | Record new import |
| `GET` | `/api/mida/imports/item/{item_id}` | Get import history for item |
| `GET` | `/api/mida/imports/{record_id}` | Get single import record |
| `PUT` | `/api/mida/imports/{record_id}` | Update record (auto-recalculates) |
| `DELETE` | `/api/mida/imports/{record_id}` | Delete record (auto-recalculates) |

### Balance Migration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/mida/migration/preview` | Preview XLSX migration |
| `POST` | `/api/mida/migration/apply` | Apply migration |

### HSCODE

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/hscode-uom/{hs_code}` | Get UOM for HS code |
| `GET` | `/api/hscode-master/lookup` | Look up HS code description |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with DB status |

---

## Frontend Pages

| Page | Route | Description |
|------|-------|-------------|
| Database View | `/database` | List, search, soft-delete/restore certificates |
| Certificate Details | `/database/certificates/:id` | View/edit certificate items, port allocation |
| Item Imports | `/database/certificates/:certId/items/:itemId/imports` | Import history, balance tracking |
| Balance Migration | `/balance-migration` | Upload historical XLSX balance sheets |
| Invoice Converter | `/invoice-converter` | 3-tab classification, K1 export |
| Certificate Parser | `/certificate-parser` | PDF OCR upload, validation, save to DB |

### Frontend Technologies

- React 18 with TypeScript
- Vite for build tooling
- React Query (`@tanstack/react-query`) for server state
- React Router v6 for navigation
- Tailwind CSS for styling
- Lucide React for icons

---

## Database

### Schema Overview

| Table | Purpose |
|-------|---------|
| `mida_certificates` | Certificate headers (number, company, dates, status) |
| `mida_certificate_items` | Line items with approved & remaining quantities per port |
| `mida_import_records` | Import ledger with balance tracking |
| `companies` | Company configuration (SST rules, dual-flag routing) |
| `hscode_uom_mappings` | HS code to UOM mapping for balance deduction |
| `hscode_master` | 25,000+ HS code reference entries |

### Migrations

The project uses Alembic with 11 versioned migrations. Run them with:

```bash
# Local
cd server && alembic upgrade head

# Docker
docker compose run --rm db-migrate

# Makefile
make db-up
```

---

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions and [QUICK_DEPLOY.md](QUICK_DEPLOY.md) for a step-by-step checklist.

### Docker Compose Services

| Service | Container | Description |
|---------|-----------|-------------|
| `kis-api` | `kis-api` | FastAPI backend |
| `kis-frontend` | `kis-frontend` | Nginx serving React build |
| `postgres` | `kis-postgres` | PostgreSQL 15 |
| `db-backup` | `kis-db-backup` | Automated daily backups |
| `db-migrate` | `kis-db-migrate` | One-shot migration runner |

### Useful Commands

```bash
make docker-build      # Build images
make docker-up         # Start services
make docker-down       # Stop services
make docker-logs       # View logs
make docker-migrate    # Run migrations
make docker-backup     # Manual backup
make docker-monitor    # Check health
```

---

## Development

### Running Tests

```bash
make test
# or
cd server && python -m pytest -v
```

### Linting & Formatting

```bash
make lint       # Check with ruff
make format     # Auto-format with ruff
```

### Creating Migrations

```bash
make db-revision MSG="describe your change"
make db-up
```

---

## License

Proprietary - All rights reserved.
