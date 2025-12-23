# MIDA Project

MIDA Certificate OCR + Quota Tracking System.

## Current Implementation Status

### ✅ Completed Features

**Certificate Parsing (TE01 Form)**
- Azure Document Intelligence integration for PDF text extraction
- **Multi-table parsing**: Parses ALL matching quota tables across the document, merges and de-duplicates items
- Text-based fallback parser for multi-page TE01 certificates
- **Page-by-page parsing**: Extracts text per page using Azure spans, parses each page separately, then merges and de-duplicates items
- Header extraction: MIDA number, company name, exemption period
- Item extraction: line number, HS code, item name, approved quantity, UOM
- **Station split parsing**: PORT_KLANG, KLIA, BUKIT_KAYU_HITAM (always includes all 3 keys)
  - Sub-header row detection for station column mapping
  - Continuation row merging for split table rows
  - Amended value extraction from noisy cells
- UOM normalization: `kg` → `KGM`, `u`/`unit`/`pcs` → `UNIT`
- **Handwritten amendment handling**: Extracts values from cells with pen crossouts and stamps
- **OCR artifact removal**: Cleans `:unselected:`, `:selected:` markers
- Debug endpoint with detailed parsing statistics

### 🔧 Parser Details

**Quantity Parsing:**
- Supports numbers with commas (e.g., `14,844.00`)
- Extracts UOM suffix (e.g., `14,844.00 kg` → qty=14844.0, uom=KGM)
- Prefers lines with UOM over numeric-only lines
- **Handles handwritten amendments**: Extracts clean numbers from noisy cells with stamps/crossouts
- **Amended value extraction**: Recognizes patterns like `239073.760 <<<<< 239,871.00` and extracts the intended value
- Leaves truly ambiguous values empty for manual review in GUI

**Station Splits:**
- **Station sub-header detection**: Finds PORT_KLANG, KLIA, BUKIT_KAYU_HITAM column headers in sub-rows
- Maps station columns correctly even when headers span multiple rows
- **Continuation row handling**: Merges data from rows split across table boundaries
- Parses station values with amended number extraction
- Handles empty stations (null values)
- **OCR artifact cleaning**: Removes `:unselected:`, `:selected:` markers from Azure DI
- **Declaration row filtering**: Skips signature/declaration rows (Nama/Name, Jawatan/Designation, etc.)

**Multi-Page Support:**
- Extracts text per page using Azure Document Intelligence spans
- Parses each page independently (avoids cross-page interference)
- Merges items across pages, de-duplicates by (line_no, hs_code)
- Sorts final items by numeric line number
- **Local PDF page count validation** using pypdf (compares against Azure pages)

## Project Structure

- `server/`: FastAPI backend
  - `app/services/azure_di_client.py`: Azure Document Intelligence client
  - `app/services/header_parser.py`: Header field extraction
  - `app/services/text_quota_parser.py`: Text-based item parsing
  - `app/services/table_parser.py`: Table-based item parsing (fallback)
  - `app/services/normalize_validate.py`: Item validation and normalization
- `web/`: Simple HTML/JS frontend
- `Templates/`: Holds local PDFs for testing (ignored by git)

## Setup Instructions

### Prerequisites
- Python 3.8+

### 1. Backend Setup

Navigate to the `server` directory:

```bash
cd server
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate the virtual environment:

- **Windows:** `venv\Scripts\activate`
- **Mac/Linux:** `source venv/bin/activate`

Install dependencies:

```bash
pip install -r requirements.txt
```

Configuration:

Copy the example environment file and add your Azure credentials:

```bash
cp .env.example .env
```

Edit `server/.env`:
```
AZURE_DI_ENDPOINT=https://YOUR_RESOURCE_NAME.cognitiveservices.azure.com/
AZURE_DI_KEY=YOUR_KEY_HERE
```

Run the server:

```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.
API Docs: `http://localhost:8000/docs`.

### 2. Frontend Usage

Simply open `web/index.html` in your browser.

You can do this by navigating to the `web` folder in your file explorer and double-clicking `index.html`.

### 3. Testing the MVP

1. Ensure the server is running.
2. Open the web page.
3. Click "Choose File" and select a PDF document.
4. Click "Parse Certificate".

### 4. Debugging via API Docs

1. Open `http://localhost:8000/docs`.
2. Find `POST /api/mida/certificate/parse-debug`.
3. Click "Try it out".
4. Upload a PDF.
5. Execute and check the Response body for extracted items, warnings, and debug info (table samples, text samples).
