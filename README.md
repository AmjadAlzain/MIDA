# MIDA Project

MIDA Certificate OCR + Quota Tracking System with PostgreSQL database backend.

## Features

- **Certificate Parsing (TE01 Form)**: Azure Document Intelligence integration for PDF text extraction
- **Multi-table parsing**: Parses ALL matching quota tables across documents
- **Page-by-page parsing**: Extracts text per page, parses separately, merges and de-duplicates
- **Station split parsing**: PORT_KLANG, KLIA, BUKIT_KAYU_HITAM support
- **Handwritten amendment handling**: Extracts values from cells with pen crossouts and stamps
- **PostgreSQL Database**: Tracks import records and exemption approvals

## Project Structure

```
MIDA/
├── server/                         # FastAPI backend
│   ├── app/
│   │   ├── main.py                # Application entry point
│   │   ├── config.py              # Settings (12-factor, env vars)
│   │   ├── logging_config.py      # Structured JSON logging
│   │   ├── routers/               # API endpoints
│   │   └── services/              # Business logic
│   │       ├── azure_di_client.py # Azure Document Intelligence
│   │       ├── header_parser.py   # Header field extraction
│   │       ├── text_quota_parser.py
│   │       ├── table_parser.py
│   │       └── normalize_validate.py
│   ├── tools/
│   │   └── db_setup/              # Database setup scripts
│   │       ├── Kagayaku_db.py     # PostgreSQL setup script
│   │       └── Kagayaku_db.ipynb  # Interactive notebook version
│   └── requirements.txt
├── web/                           # Simple HTML/JS frontend
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

API Docs: `http://localhost:8000/docs`

## Frontend

Open `web/index.html` in your browser to use the simple upload interface.
