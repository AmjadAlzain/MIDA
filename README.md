# Kagayaku Database Setup

A Python-based database initialization tool for managing MIDA (Malaysian Investment Development Authority) import tracking data using PostgreSQL.

## Overview

This project provides scripts to set up and manage a PostgreSQL database for tracking:
- **Import records** - Tracking imported goods with customs declarations
- **Exemption records** - Managing tax exemption approvals and balances

## Files

| File | Description |
|------|-------------|
| `Kagayaku_db.py` | Main Python script for database setup |
| `Kagayaku_db.ipynb` | Jupyter Notebook version with interactive execution |
| `Kagayaku.session.sql` | SQL session file for SQLTools |

## Database Schema

### Database: `mida`

#### Table1 - Import Records
| Column | Type | Description |
|--------|------|-------------|
| S_No | INTEGER | Primary key |
| Import_Date | DATE | Date of import |
| MIDA_NO | VARCHAR(255) | MIDA reference number |
| Company_Name | VARCHAR(255) | Importing company name |
| Declaration_Reg_No | VARCHAR(255) | Customs declaration number |
| Kagayaku_Ref_No | VARCHAR(255) | Internal reference number |
| HsCode | VARCHAR(255) | Harmonized System code |
| Item_Name | VARCHAR(255) | Name of imported item |
| Balance_Carried_Forward | DECIMAL(10,2) | Previous balance |
| Quantity | REAL | Imported quantity |
| Balance | DECIMAL(10,2) | Current balance |

#### Table2 - Exemption Records
| Column | Type | Description |
|--------|------|-------------|
| S_No | INTEGER | Primary key |
| MIDA_NO | VARCHAR(255) | MIDA reference number |
| Company_Name | VARCHAR(255) | Company name |
| HsCode | VARCHAR(255) | Harmonized System code |
| Item_Name | VARCHAR(255) | Item name |
| Approved_Quantity | DECIMAL(10,2) | Approved exemption quantity |
| Remaining_Quantity | DECIMAL(10,2) | Remaining exemption balance |
| Date_of_exempt | DATE | Exemption approval date |
| Exemption_start_date | DATE | Exemption period start |
| Exemption_end_date | DATE | Exemption period end |

## Requirements

- Python 3.x
- PostgreSQL server
- Required packages (see `requirements.txt`):
  - `psycopg2-binary` - PostgreSQL adapter
  - `pandas` - Data manipulation
  - `ipykernel` - Jupyter kernel support

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Ensure PostgreSQL is running on localhost:5432

3. Update credentials in the script if needed:
   ```python
   DB_HOST = "localhost"
   DB_PORT = 5432
   DB_USER = "postgres"
   DB_PASSWORD = "your_password"
   DB_NAME = "mida"
   ```

## Usage

### Running the Script
```bash
python Kagayaku_db.py
```

### Using Jupyter Notebook
Open `Kagayaku_db.ipynb` and run the cells sequentially.

### SQLTools Connection (VS Code)
Configure a new PostgreSQL connection with:
- **Connection Name**: `Kagayaku`
- **Database**: `mida`
- **Host**: `localhost`
- **Port**: `5432`
- **User**: `postgres`

## Features

- **Automatic database creation** - Creates the `mida` database if it doesn't exist
- **Table initialization** - Sets up required tables with proper schema
- **Error handling** - Graceful handling of existing databases/tables
- **Flexible SQL generation** - Utility function for generating custom table schemas

## License

Internal use only.
