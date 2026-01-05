# MIDA Project

MIDA Certificate OCR + Invoice Matching + 3-Tab Classification System + Quota Tracking with PostgreSQL database backend.

## Features

- **3-Tab Classification System**: Classify invoice items into Form-D, MIDA, and Duties Payable categories
- **Company-Specific Rules**: HICOM and Hong Leong have different SST and routing rules
- **K1 XLS Export**: Export classified items to K1 Import format with proper duty/SST settings
- **Certificate Parsing (TE01 Form)**: Azure Document Intelligence integration for PDF text extraction
- **Invoice Matching**: Match invoice items against MIDA certificate quotas
- **Multi-Certificate Matching**: Match items against multiple MIDA certificates simultaneously
- **HSCODE UOM Mapping**: Determine balance deduction units (UNIT or KGM) by HSCODE
- **Multi-table parsing**: Parses ALL matching quota tables across documents
- **Page-by-page parsing**: Extracts text per page, parses separately, merges and de-duplicates
- **Station split parsing**: PORT_KLANG, KLIA, BUKIT_KAYU_HITAM support
- **Handwritten amendment handling**: Extracts values from cells with pen crossouts and stamps
- **PostgreSQL Database**: Tracks import records and exemption approvals
- **REST API**: Clean separation between services via HTTP API calls

## Project Structure

```
MIDA/
├── server/                              # FastAPI backend
│   ├── app/
│   │   ├── main.py                     # Application entry point
│   │   ├── config.py                   # Settings (12-factor, env vars)
│   │   ├── logging_config.py           # Structured JSON logging
│   │   ├── clients/
│   │   │   └── mida_client.py          # MIDA API client with caching
│   │   ├── db/
│   │   │   ├── base.py                 # SQLAlchemy Base
│   │   │   ├── mixins.py               # UUID, Timestamp mixins
│   │   │   └── session.py              # Database session
│   │   ├── models/
│   │   │   ├── company.py              # Company model (SST rules)
│   │   │   ├── hscode_uom_mapping.py   # HSCODE to UOM mapping
│   │   │   └── mida_certificate.py     # Certificate & items
│   │   ├── repositories/               # Data access layer
│   │   │   ├── company_repo.py
│   │   │   ├── hscode_uom_repo.py
│   │   │   ├── mida_certificate_repo.py
│   │   │   └── mida_import_repo.py
│   │   ├── routers/                    # API endpoints
│   │   │   ├── convert.py              # Main conversion endpoints
│   │   │   ├── hscode_uom.py           # HSCODE UOM endpoints
│   │   │   ├── mida_certificate.py     # Certificate parsing
│   │   │   ├── mida_certificates.py    # Certificate CRUD
│   │   │   └── mida_imports.py         # Import tracking
│   │   ├── schemas/                    # Pydantic schemas
│   │   │   ├── classification.py       # 3-tab classification schemas
│   │   │   ├── convert.py              # Conversion schemas
│   │   │   ├── mida_certificate.py     # Certificate schemas
│   │   │   └── mida_import.py          # Import schemas
│   │   └── services/                   # Business logic
│   │       ├── azure_di_client.py      # Azure Document Intelligence
│   │       ├── invoice_classification_service.py  # Classification logic
│   │       ├── k1_export_service.py    # K1 XLS generation
│   │       ├── mida_certificate_service.py
│   │       ├── mida_import_service.py
│   │       ├── mida_matcher.py         # Invoice-to-MIDA matching
│   │       └── mida_matching_service.py
│   ├── alembic/                        # Database migrations
│   │   └── versions/                   # 8 migration files
│   ├── templates/
│   │   └── K1_Import_Template.xls      # K1 export template
│   ├── tests/                          # Unit and integration tests
│   ├── tools/
│   │   └── db_setup/                   # Database setup scripts
│   ├── run_server.py                   # Quick server startup script
│   └── requirements.txt
├── web/                                # Simple HTML/JS frontend
│   └── index.html                      # Web UI with 3-tab classification
├── Makefile                            # Common commands
├── DEVELOPMENT_PLAN.md                 # Development plan & progress
├── DEPLOYMENT.md                       # Deployment guide
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ (for database features)

### Using Makefile (Recommended)

```bash
# Install dependencies
make install

# Set up environment
cp .env.example server/.env
# Edit server/.env with your Azure and database credentials

# Run the server
make run

# Run tests
make test

# Lint code
make lint
```

### Manual Setup

```bash
cd server
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
cp ../.env.example .env
# Edit .env with your credentials

uvicorn app.main:app --reload --port 8000
```

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `AZURE_DI_ENDPOINT` | Azure Document Intelligence endpoint | (required) |
| `AZURE_DI_KEY` | Azure Document Intelligence API key | (required) |
| `DATABASE_URL` | PostgreSQL connection URL | (required for features) |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |
| `LOG_FORMAT` | Log format (json, text) | json |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | * |

## Database Setup

The PostgreSQL database tracks certificates, import records, companies, and HSCODE mappings.

```bash
# Run database migrations
cd server && alembic upgrade head

# Or use Makefile
make db-up
```

### Database Schema

- **mida_certificates**: Certificate master records
- **mida_certificate_items**: Certificate line items with remaining quantities
- **mida_import_records**: Import transaction ledger
- **companies**: HICOM and Hong Leong company configurations
- **hscode_uom_mappings**: HSCODE to UOM mapping for balance deduction

## API Endpoints

### Main Endpoints
- `GET /` - Root endpoint
- `GET /health` - Health check
- `GET /api/companies` - **List all companies**
- `POST /api/convert/classify` - **3-Tab Classification** (Form-D, MIDA, Duties Payable)
- `POST /api/convert/export-classified` - **Export classified items to K1 XLS**
- `POST /api/convert` - Invoice conversion with MIDA certificate matching
- `POST /api/convert-multi` - Multi-certificate MIDA matching

### Certificate Endpoints
- `GET /api/mida/certificates/` - List certificates
- `POST /api/mida/certificates/draft` - Create/update draft certificate
- `POST /api/mida/certificate/parse` - Parse certificate PDF
- `POST /api/mida/certificate/parse-debug` - Parse with debug info

API Docs: `http://localhost:8000/docs`

---

## 3-Tab Classification System

The `/api/convert/classify` endpoint classifies invoice items into 3 categories:

### Classification Rules

| Form-D Flag | MIDA Matched | Result |
|-------------|--------------|--------|
| Yes | No | **Form-D** table |
| No | Yes | **MIDA** table |
| Yes | Yes | Depends on company |
| No | No | **Duties Payable** table |

### Company-Specific Rules

**HICOM YAMAHA MOTOR SDN BHD:**
- Dual-flagged items → Form-D table
- SST exemption ON for all items in all tables

**HONG LEONG YAMAHA MOTOR SDN BHD:**
- Dual-flagged items → MIDA table
- SST exemption ON only for MIDA table items

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file` | File | Yes | - | Invoice file (Excel .xls/.xlsx) |
| `company_id` | UUID | Yes | - | Company UUID for classification rules |
| `mida_certificate_ids` | string | No | - | Comma-separated certificate UUIDs |
| `country` | string | No | `JP` | Country of origin code |
| `port` | string | No | `port_klang` | Import port |
| `import_date` | string | No | - | Import date (YYYY-MM-DD) |
| `match_mode` | string | No | `fuzzy` | `exact` or `fuzzy` matching |
| `match_threshold` | float | No | `0.88` | Minimum similarity score (0.0-1.0) |

### Response Schema

```json
{
  "company": {
    "id": "uuid",
    "name": "HICOM YAMAHA MOTOR SDN BHD",
    "sst_default_behavior": "all_on",
    "dual_flag_routing": "form_d"
  },
  "country": "JP",
  "port": "port_klang",
  "import_date": "2025-01-15",
  "form_d_items": [...],
  "mida_items": [...],
  "duties_payable_items": [...],
  "total_items": 50,
  "form_d_count": 20,
  "mida_count": 25,
  "duties_payable_count": 5,
  "warnings": []
}
```

---

## K1 XLS Export

The `/api/convert/export-classified` endpoint exports items to K1 Import format.

### Export Types

| Type | Import Duty | SST |
|------|-------------|-----|
| `form_d` | Exemption (100%) | Per item's `sst_exempted` |
| `mida` | Exemption (100%) | Per item's `sst_exempted` |
| `duties_payable` | Empty (no exemption) | Per item's `sst_exempted` |

### Request Body

```json
{
  "items": [
    {
      "hs_code": "84713010",
      "description": "Computer parts",
      "description2": "100",
      "quantity": 100,
      "uom": "UNT",
      "amount": 5000.00,
      "net_weight_kg": 50.5,
      "sst_exempted": true
    }
  ],
  "export_type": "form_d",
  "country": "MY"
}
```

---

---

## MIDA Matching Mode (Legacy)

The `/api/convert` endpoint enables matching invoice items against MIDA certificate quotas.

### How It Works

1. **Upload Invoice**: Upload an Excel or CSV file containing invoice items
2. **Specify Certificate**: Provide the MIDA certificate number to match against
3. **Item Matching**: The system matches each invoice item to MIDA certificate items using:
   - **Exact mode**: HS codes must match exactly (normalized)
   - **Fuzzy mode** (default): Uses HS code prefix matching + description similarity
4. **Quota Checking**: Computes remaining quantities and warns about limits
5. **Response**: Returns matched items with MIDA details, remaining quantities, and warnings

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file` | File | Yes | - | Invoice file (Excel .xls/.xlsx or CSV) |
| `mida_certificate_number` | string | Yes | - | MIDA certificate number to match against |
| `match_mode` | string | No | `fuzzy` | `exact` or `fuzzy` matching |
| `match_threshold` | float | No | `0.88` | Minimum similarity score for fuzzy matches (0.0-1.0) |

### Response Schema

```json
{
  "mida_certificate_number": "MIDA/123/2024",
  "mida_matched_items": [
    {
      "line_no": 1,
      "hs_code": "84715000",
      "description": "Computer parts",
      "quantity": 100,
      "uom": "UNT",
      "amount": 5000.00,
      "net_weight_kg": 50.5,
      "mida_line_no": 3,
      "mida_hs_code": "84715000",
      "mida_item_name": "COMPUTER PROCESSING UNIT",
      "remaining_qty": 400,
      "remaining_uom": "UNIT",
      "match_score": 0.92,
      "approved_qty": 500
    }
  ],
  "warnings": [
    {
      "invoice_item": "Line 5: Motor parts",
      "reason": "Insufficient remaining qty: requested 200, remaining 50",
      "severity": "error"
    }
  ],
  "total_invoice_items": 10,
  "matched_item_count": 8,
  "unmatched_item_count": 2
}
```

### Warning Severities

| Severity | Meaning |
|----------|---------|
| `info` | Informational (e.g., limit reached after this item) |
| `warning` | Potential issue (e.g., no matching MIDA item found) |
| `error` | Critical issue (e.g., insufficient remaining quantity) |

### Example Usage

```bash
# Using curl
curl -X POST "http://localhost:8000/api/convert" \
  -F "file=@invoice.xlsx" \
  -F "mida_certificate_number=MIDA/123/2024" \
  -F "match_mode=fuzzy" \
  -F "match_threshold=0.85"

# Using Python requests
import requests

files = {"file": open("invoice.xlsx", "rb")}
data = {
    "mida_certificate_number": "MIDA/123/2024",
    "match_mode": "fuzzy",
    "match_threshold": 0.85
}
response = requests.post("http://localhost:8000/api/convert", files=files, data=data)
print(response.json())
```

### Error Responses

| Status | Condition |
|--------|-----------|
| `422` | Empty certificate number, invalid file, missing required columns |
| `404` | MIDA certificate not found in database |
| `500` | Unexpected server error |

## Frontend

Open `web/index.html` in your browser to use the simple upload interface.
