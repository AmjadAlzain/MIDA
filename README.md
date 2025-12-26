# MIDA Project

MIDA Certificate OCR + Invoice Matching + Quota Tracking System with PostgreSQL database backend.

## Features

- **Certificate Parsing (TE01 Form)**: Azure Document Intelligence integration for PDF text extraction
- **Invoice Matching**: Match invoice items against MIDA certificate quotas
- **Multi-table parsing**: Parses ALL matching quota tables across documents
- **Page-by-page parsing**: Extracts text per page, parses separately, merges and de-duplicates
- **Station split parsing**: PORT_KLANG, KLIA, BUKIT_KAYU_HITAM support
- **Handwritten amendment handling**: Extracts values from cells with pen crossouts and stamps
- **PostgreSQL Database**: Tracks import records and exemption approvals
- **REST API**: Clean separation between services via HTTP API calls

## Project Structure

```
MIDA/
├── server/                         # FastAPI backend
│   ├── app/
│   │   ├── main.py                # Application entry point
│   │   ├── config.py              # Settings (12-factor, env vars)
│   │   ├── logging_config.py      # Structured JSON logging
│   │   ├── clients/               # External API clients
│   │   │   └── mida_client.py     # MIDA API client with caching
│   │   ├── routers/               # API endpoints
│   │   │   ├── convert.py         # Invoice conversion endpoint
│   │   │   └── mida_certificate.py # Certificate parsing endpoints
│   │   ├── schemas/               # Pydantic schemas
│   │   │   └── convert.py         # Conversion request/response schemas
│   │   └── services/              # Business logic
│   │       ├── azure_di_client.py # Azure Document Intelligence
│   │       ├── mida_matcher.py    # Invoice-to-MIDA matching logic
│   │       ├── mida_matching_service.py # Invoice parsing service
│   │       ├── header_parser.py   # Header field extraction
│   │       ├── text_quota_parser.py
│   │       ├── table_parser.py
│   │       └── normalize_validate.py
│   ├── tests/                      # Unit and integration tests
│   ├── tools/
│   │   └── db_setup/              # Database setup scripts
│   ├── run_server.py              # Quick server startup script
│   └── requirements.txt
├── web/                           # Simple HTML/JS frontend
│   └── index.html                 # Web UI for invoice conversion
├── Templates/                     # Local PDFs for testing (gitignored)
├── Makefile                       # Common commands
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
| `DATABASE_URL` | PostgreSQL connection URL | (optional) |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |
| `LOG_FORMAT` | Log format (json, text) | json |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | * |

## Database Setup

The PostgreSQL database tracks import records and exemption approvals.

```bash
# Run database setup script
cd server/tools/db_setup
python Kagayaku_db.py
```

Or use the interactive Jupyter notebook: `server/tools/db_setup/Kagayaku_db.ipynb`

### Database Schema

- **Table1**: Import records (S_No, Import_Date, MIDA_NO, Company_Name, etc.)
- **Table2**: Exemption records (S_No, MIDA_NO, Approved_Quantity, Exemption dates, etc.)

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /api/mida/certificate/parse` - Parse certificate PDF
- `POST /api/mida/certificate/parse-debug` - Parse with debug info
- `POST /api/convert` - **Convert invoice with MIDA certificate matching**

API Docs: `http://localhost:8000/docs`

## MIDA Matching Mode

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
