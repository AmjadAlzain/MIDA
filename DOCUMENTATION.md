# Kagayaku Import System (KIS) - Technical Documentation

This document provides comprehensive technical documentation for developers and administrators.

---

## Table of Contents

- [System Overview](#system-overview)
- [Backend Architecture](#backend-architecture)
- [Frontend Architecture](#frontend-architecture)
- [Database Schema](#database-schema)
- [OCR Certificate Parsing](#ocr-certificate-parsing)
- [3-Tab Classification System](#3-tab-classification-system)
- [K1 Export Service](#k1-export-service)
- [Import Quota Tracking](#import-quota-tracking)
- [Balance Sheet Migration](#balance-sheet-migration)
- [Balance Sheet Export](#balance-sheet-export)
- [MIDA Matching Engine](#mida-matching-engine)
- [Security](#security)
- [API Endpoint Reference](#api-endpoint-reference)
- [Configuration Reference](#configuration-reference)

---

## System Overview

The Kagayaku Import System (KIS) automates the workflow for managing Malaysian Investment Development Authority (MIDA) import duty exemption certificates. The system handles:

1. **Certificate Digitisation**: Upload scanned PDF certificates and extract structured data via Azure Document Intelligence OCR
2. **Invoice Classification**: Upload invoice spreadsheets and automatically classify items into Form-D, MIDA, or Duties Payable categories
3. **K1 Export**: Generate K1 Import format XLS files for customs declaration
4. **Quota Tracking**: Track import quantities against certificate limits with per-port breakdown
5. **Balance Migration**: Import historical balance sheet data from XLSX files

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 18, TypeScript, Vite | Single-page application |
| Styling | Tailwind CSS | Utility-first CSS |
| State Management | React Query | Server state caching |
| Backend | FastAPI (Python 3.10+) | REST API server |
| ORM | SQLAlchemy 2.0 | Database abstraction |
| Migrations | Alembic | Schema versioning |
| Database | PostgreSQL 15 | Persistent storage |
| OCR | Azure Document Intelligence | PDF text extraction |
| Deployment | Docker Compose, Nginx | Containerised hosting |

---

## Backend Architecture

The backend follows a layered architecture:

```
Routers (HTTP handlers)
    |
Schemas (Pydantic validation)
    |
Services (Business logic)
    |
Repositories (Data access)
    |
Models (SQLAlchemy ORM)
    |
Database (PostgreSQL)
```

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `app/routers/` | FastAPI route handlers — thin layer that delegates to services |
| `app/schemas/` | Pydantic models for request/response validation |
| `app/services/` | Business logic (classification, matching, OCR, export) |
| `app/repositories/` | Database queries encapsulated behind repository pattern |
| `app/models/` | SQLAlchemy ORM models mapping to database tables |
| `app/db/` | Database engine, session factory, and mixins (UUID, timestamps) |
| `app/clients/` | HTTP clients for external APIs |
| `app/config.py` | Pydantic Settings — all config from environment variables |

### Configuration

All settings are loaded from environment variables via `app/config.py` using Pydantic Settings. The `Settings` class defines defaults and validation. Settings are cached via `@lru_cache` in `get_settings()`.

### Logging

Structured JSON logging is configured in `app/logging_config.py`. In production (`LOG_FORMAT=json`), logs are machine-parseable. In development (`LOG_FORMAT=text`), logs are human-readable.

---

## Frontend Architecture

### Pages

| Component | Route | Purpose |
|-----------|-------|---------|
| `DatabaseView` | `/database` | Certificate list with search, pagination, Active/Deleted tabs |
| `CertificateDetails` | `/database/certificates/:id` | Certificate detail view with inline item editing |
| `ItemImports` | `/database/certificates/:certId/items/:itemId/imports` | Import history per certificate item |
| `BalanceMigration` | `/balance-migration` | Historical balance sheet XLSX upload |
| `InvoiceConverter` | `/invoice-converter` | 3-tab classification UI with K1 export |
| `CertificateParser` | `/certificate-parser` | PDF upload, OCR parsing, validation |

### Service Layer

API calls are centralised in `frontend/src/services/`:

| Service | Responsibility |
|---------|----------------|
| `api.ts` | Axios instance with base URL configuration |
| `certificateService.ts` | Certificate CRUD, confirm, delete, restore |
| `importService.ts` | Import record CRUD |
| `classificationService.ts` | Invoice classification and K1 export |
| `companyService.ts` | Company listing |
| `migrationService.ts` | Balance sheet migration |

### Type System

All TypeScript interfaces are defined in `frontend/src/types/index.ts`, including: `Certificate`, `CertificateItem`, `ImportRecord`, `ClassifiedItem`, `Company`, etc.

---

## Database Schema

### Entity Relationship

```
mida_certificates (1) ---< (N) mida_certificate_items (1) ---< (N) mida_import_records
companies
hscode_uom_mappings
hscode_master
```

### Tables

#### `mida_certificates`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `certificate_number` | VARCHAR | MIDA certificate number |
| `company_name` | VARCHAR | Company name |
| `exemption_start_date` | DATE | Exemption period start |
| `exemption_end_date` | DATE | Exemption period end |
| `status` | VARCHAR | `draft` or `confirmed` |
| `model_number` | VARCHAR | Model number (optional) |
| `is_deleted` | BOOLEAN | Soft delete flag |
| `source_filename` | VARCHAR | Original PDF filename |
| `raw_ocr_json` | JSON | Raw OCR output for debugging |

#### `mida_certificate_items`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `certificate_id` | UUID | FK to certificates |
| `line_no` | VARCHAR | Item line number |
| `hs_code` | VARCHAR | HS code (e.g., 7318.15.9000) |
| `item_name` | VARCHAR | Item description |
| `uom` | VARCHAR | Unit of measure (KGM, UNIT) |
| `approved_quantity` | DECIMAL | Total approved quantity |
| `remaining_quantity` | DECIMAL | Remaining across all ports |
| `port_klang_qty` | DECIMAL | Approved for Port Klang |
| `klia_qty` | DECIMAL | Approved for KLIA |
| `bukit_kayu_hitam_qty` | DECIMAL | Approved for Bukit Kayu Hitam |
| `remaining_port_klang` | DECIMAL | Remaining for Port Klang |
| `remaining_klia` | DECIMAL | Remaining for KLIA |
| `remaining_bukit_kayu_hitam` | DECIMAL | Remaining for Bukit Kayu Hitam |
| `is_dummy` | BOOLEAN | Placeholder entry flag |
| `is_deleted` | BOOLEAN | Soft delete flag |

#### `mida_import_records`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `certificate_item_id` | UUID | FK to certificate items |
| `port` | VARCHAR | Import port |
| `quantity_imported` | DECIMAL | Quantity imported |
| `balance_before` | DECIMAL | Balance before this import |
| `balance_after` | DECIMAL | Balance after this import |
| `import_date` | DATE | Date of import |
| `declaration_form_reg_no` | VARCHAR | Declaration form registration number |
| `remarks` | TEXT | Optional notes |

#### `companies`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `name` | VARCHAR | Company name |
| `sst_default_behavior` | VARCHAR | `all_on` or `mida_only` |
| `dual_flag_routing` | VARCHAR | `form_d` or `mida` |

#### `hscode_uom_mappings`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `hs_code` | VARCHAR | Normalised HS code (dots removed) |
| `uom` | VARCHAR | `UNIT` or `KGM` |

### Alembic Migrations

| # | File | Description |
|---|------|-------------|
| 001 | `001_mida_certificates.py` | Certificate and item tables |
| 002 | `002_mida_import_tracking.py` | Import ledger table |
| 003 | `003_update_certificate_status.py` | Status column |
| 004 | `004_add_declaration_form_reg_no.py` | Declaration form field |
| 005 | `005_add_model_number.py` | Model number field |
| 006 | `006_add_soft_delete.py` | Soft delete flag |
| 007 | `007_hscode_uom_mappings.py` | HS code to UOM table |
| 008 | `008_companies.py` | Companies table |
| 009 | `009_hscode_master.py` | HS code master reference (25K+ entries) |
| 010 | `010_add_dummy_flag.py` | Dummy entry flag |
| 011 | `011_rename_invoice_to_declaration.py` | Rename invoice_number to declaration_form_reg_no |

---

## OCR Certificate Parsing

### Overview

The certificate parsing pipeline uses Azure Document Intelligence to extract text from scanned MIDA certificate PDFs (TE01 forms), then applies custom parsers to extract structured data.

### Pipeline

```
PDF Upload
    |
    v
Azure Document Intelligence (Layout model)
    |
    v
extract_page_texts()  -- text per page from Azure spans
    |
    v
Table Parser (primary) OR Text Parser (fallback)
    |
    v
merge_items_from_pages()  -- de-duplicate by (line_no, hs_code)
    |
    v
Header Parser  -- extract certificate number, company, dates
    |
    v
normalize_validate()  -- validate required fields
    |
    v
JSON Response
```

### Parsers

#### Header Parser (`header_parser.py`)
- Extracts MIDA number via regex: `CDE\d?/\d{4}/\d+`
- Extracts company name with smart lookahead
- Extracts exemption period (start/end dates)

#### Table Parser (`table_parser.py`)
- Primary parser for structured certificates
- Scores table headers to identify quota tables (threshold >= 2)
- Detects station sub-headers (PORT_KLANG, KLIA, BUKIT_KAYU_HITAM)
- Handles continuation rows (items spanning multiple table rows)
- Extracts amended values from noisy cells (stamps, pen crossouts)
- Cleans OCR artifacts (`:unselected:`, `:selected:` markers)
- Falls back to text parser if no items found

#### Text Parser (`text_quota_parser.py`)
- Fallback parser for unstructured text
- Uses HS code pattern as anchors: `\d{4}\.\d{2}\.\d{4}`
- Page-by-page parsing to avoid cross-page interference
- UOM normalisation: kg -> KGM, u/unit/pcs -> UNIT

### OCR Output Format

```json
{
  "mida_no": "CDE2/2024/00755",
  "company_name": "COMPANY NAME",
  "exemption_start": "2024-07-19",
  "exemption_end": "2027-07-18",
  "items": [
    {
      "line_no": "1",
      "hs_code": "7318.15.9000",
      "item_name": "BOLT, FLG.",
      "approved_quantity": 14844.0,
      "uom": "KGM",
      "station_split": {
        "PORT_KLANG": 1484.4,
        "KLIA": null,
        "BUKIT_KAYU_HITAM": 13359.6
      }
    }
  ],
  "warnings": []
}
```

---

## 3-Tab Classification System

### Flow

1. User uploads an invoice Excel file
2. User selects a company and optionally one or more MIDA certificates
3. System parses all invoice items
4. System matches items against selected MIDA certificates (fuzzy HS code + description matching)
5. System classifies each item based on Form-D flag and MIDA match status

### Classification Rules

| Form-D Flag | MIDA Matched | HICOM Result | Hong Leong Result |
|-------------|--------------|--------------|-------------------|
| Yes | No | Form-D | Form-D |
| No | Yes | MIDA | MIDA |
| Yes | Yes | **Form-D** | **MIDA** |
| No | No | Duties Payable | Duties Payable |

### SST Rules

| Company | SST Behaviour |
|---------|---------------|
| HICOM YAMAHA MOTOR SDN BHD | SST exemption ON for all items in all tables |
| HONG LEONG YAMAHA MOTOR SDN BHD | SST exemption ON only for MIDA table items |

---

## K1 Export Service

The K1 export generates XLS files using the K1 Import Template.

### Column Mapping

| Source Field | Template Column |
|-------------|-----------------|
| Country Code | CountryOfOrigin |
| HS Code (normalised) | HSCode |
| UOM | StatisticalUOM, DeclaredUOM |
| Quantity | StatisticalQty, DeclaredQty |
| Amount | ItemAmount |
| Description | ItemDescription |

### Export Types

| Type | Import Duty | SST |
|------|-------------|-----|
| `form_d` | Exemption (E, 100%) | Per item setting |
| `mida` | Exemption (E, 100%) | Per item setting |
| `duties_payable` | None | Per item setting |

---

## Import Quota Tracking

### Recording Imports

When an import is recorded via `POST /api/mida/imports`:
1. The system checks the certificate item's remaining quantity for the specified port
2. Records the import with `balance_before` and `balance_after` values
3. Updates the item's `remaining_*` quantities

### Auto-Recalculation

When an import record is edited or deleted:
1. `recalculate_item_port_balances()` recalculates the balance chain for all imports on that item/port
2. `recalculate_item_remaining_quantities()` updates the item's remaining quantities
3. Uses `SELECT FOR UPDATE` database locking to prevent race conditions
4. Orders by `import_date` with `created_at` as tie-breaker

### Port Support

| Port | Key |
|------|-----|
| Port Klang | `port_klang` |
| KLIA | `klia` |
| Bukit Kayu Hitam | `bukit_kayu_hitam` |

---

## Balance Sheet Migration

### Workflow

1. User selects a MIDA certificate and uploads an XLSX balance sheet
2. System previews the migration, matching XLSX items to certificate items
3. If the XLSX contains a different certificate number, user can choose which certificate to use
4. User confirms the migration, resolving any conflicts
5. System creates import records from the historical data

### Features

- Certificate mismatch detection and resolution
- Decimal parsing with unit suffix stripping (KGS, KGM, UNT, etc.)
- Date parsing with comma typo handling
- Eager loading to prevent N+1 query issues
- 10-minute API timeout for large uploads

---

## Balance Sheet Export

### MIDA Template Format

The system generates XLSX balance sheets matching the official MIDA template:

- **Font**: Times New Roman (18pt title, 24pt labels, 22pt data)
- **Headers**: Two-row headers (rows 13-14) with medium borders
- **Columns**: TARIKH IMPORT, NO DAFTAR BORANG IKRAR, BAKI DI BAWA KEHADAPAN, KUANTITI, BAKI, T/TANGAN PIK/PNK
- **Sheets**: One sheet per certificate item, named "ItemName (line_no)"
- **Port-specific**: Export per port (Port Klang, KLIA, Bukit Kayu Hitam)

---

## MIDA Matching Engine

### Algorithm

The matching engine (`mida_matcher.py`) matches invoice items to MIDA certificate items:

1. **HS Code Matching**: Normalise both codes (remove dots, trailing zeros) and compare
2. **Description Matching**: Fuzzy string similarity using text normalisation (casefold, strip punctuation, collapse spaces)
3. **Scoring**: Combined score from HS code match + description similarity
4. **1-to-1 Constraint**: Each MIDA item can only be matched once
5. **Tie-breaking**: Higher score wins; prefer exact matches; lower line number breaks ties

### Matching Modes

| Mode | Behaviour |
|------|-----------|
| `exact` | HS codes must match exactly after normalisation |
| `fuzzy` | HS code prefix matching + description similarity (default threshold: 0.88) |

### Warnings

| Severity | Condition |
|----------|-----------|
| `info` | Limit reached after this import |
| `warning` | No matching MIDA item found |
| `error` | Insufficient remaining quantity |

---

## Security

### IP Whitelisting

Two-layer IP whitelisting:

1. **FastAPI middleware** (`server/app/main.py`): Checks `ALLOWED_NETWORKS` env var. Localhost and Docker networks are always allowed.
2. **Nginx** (`frontend/nginx.conf`): Optional `allow`/`deny` directives (commented out by default — uncomment and configure for production).

### CORS

Configured via `CORS_ORIGINS` environment variable. In production, set to specific domain(s).

### Authentication

The current version does not include user authentication. For production use, consider adding:
- API key authentication
- OAuth2/JWT tokens
- Reverse proxy authentication

---

## API Endpoint Reference

### Conversion & Classification (`/api/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/companies` | List all companies |
| `POST` | `/api/convert` | Single-certificate MIDA matching |
| `POST` | `/api/convert-multi` | Multi-certificate MIDA matching |
| `POST` | `/api/convert/classify` | 3-tab invoice classification |
| `POST` | `/api/convert/export-classified` | K1 XLS export |

### Certificate CRUD (`/api/mida/certificates/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/mida/certificates/` | List certificates (paginated, filterable) |
| `GET` | `/api/mida/certificates/{id}` | Get certificate with items |
| `POST` | `/api/mida/certificates/draft` | Create/update draft certificate |
| `PUT` | `/api/mida/certificates/{id}` | Update draft |
| `POST` | `/api/mida/certificates/{id}/confirm` | Confirm (lock) certificate |
| `DELETE` | `/api/mida/certificates/{id}` | Soft-delete |
| `POST` | `/api/mida/certificates/{id}/restore` | Restore soft-deleted |
| `DELETE` | `/api/mida/certificates/{id}/hard` | Permanent delete |

### Certificate Parsing (`/api/mida/certificate/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/mida/certificate/parse` | Parse PDF via OCR |
| `POST` | `/api/mida/certificate/parse-debug` | Parse with debug statistics |

### Import Tracking (`/api/mida/imports/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/mida/imports` | Record new import |
| `GET` | `/api/mida/imports/item/{item_id}` | Get import history |
| `GET` | `/api/mida/imports/{record_id}` | Get single record |
| `PUT` | `/api/mida/imports/{record_id}` | Update (auto-recalculates) |
| `DELETE` | `/api/mida/imports/{record_id}` | Delete (auto-recalculates) |

### Balance Migration (`/api/mida/migration/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/mida/migration/preview` | Preview XLSX migration |
| `POST` | `/api/mida/migration/apply` | Apply migration |
| `POST` | `/api/mida/migration/fix-remaining-quantities/{id}` | Recalculate remaining |

### HS Code (`/api/hscode-uom/`, `/api/hscode-master/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/hscode-uom/{hs_code}` | Get UOM for HS code |
| `GET` | `/api/hscode-master/lookup` | Look up HS code description |
| `POST` | `/api/hscode-master/seed` | Seed HS code master data |

### Health (`/health`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with DB status |

---

## Configuration Reference

All configuration is via environment variables, loaded by `app/config.py`.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `APP_NAME` | str | `KIS API` | Application name |
| `APP_VERSION` | str | `1.0.0` | Application version |
| `ENVIRONMENT` | str | `development` | `development`, `staging`, `production` |
| `DEBUG` | bool | `false` | Enable debug mode |
| `HOST` | str | `0.0.0.0` | Server bind host |
| `PORT` | int | `8000` | Server bind port |
| `DATABASE_URL` | str | `None` | PostgreSQL connection URL |
| `AZURE_DI_ENDPOINT` | str | *(required)* | Azure Document Intelligence endpoint |
| `AZURE_DI_KEY` | str | *(required)* | Azure Document Intelligence API key |
| `CORS_ORIGINS` | str | `*` | Comma-separated allowed origins |
| `ALLOWED_NETWORKS` | str | *(empty)* | Comma-separated CIDR ranges for IP whitelisting |
| `LOG_LEVEL` | str | `INFO` | Logging level |
| `LOG_FORMAT` | str | `json` | `json` or `text` |
| `WORKERS` | int | `4` | Number of API workers |
| `API_PORT` | int | `8000` | Docker-mapped API port |
| `FRONTEND_PORT` | int | `80` | Docker-mapped frontend port |
| `POSTGRES_USER` | str | `mida` | PostgreSQL username |
| `POSTGRES_PASSWORD` | str | *(required)* | PostgreSQL password |
| `POSTGRES_DB` | str | `mida` | PostgreSQL database name |
| `BACKUP_RETENTION_DAYS` | int | `7` | Days to retain backups |
| `MIDA_API_BASE_URL` | str | `None` | External MIDA API URL (optional) |
| `MIDA_API_TIMEOUT_SECONDS` | int | `10` | MIDA API request timeout |
| `MIDA_API_CACHE_TTL_SECONDS` | int | `60` | MIDA API cache TTL |
