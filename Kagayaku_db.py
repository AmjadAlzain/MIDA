# Kagayaku Database Setup

## 1. Connect to PostgreSQL and Create Database
import psycopg2
from psycopg2 import sql, errors

# PostgreSQL error codes (SQLSTATE)
# 42P04 = duplicate_database
# 28P01 = invalid_password
# 3D000 = invalid_catalog_name (database does not exist)
# 42P07 = duplicate_table

# --- User Credentials ---
DB_HOST = "localhost"
DB_PORT = 5432
DB_USER = "postgres"
DB_PASSWORD = "7476"
DB_NAME = "mida"
# SQLTOOLS_CONNECTION_NAME = "Kagayaku" # Not used in pure Python script

def create_database(conn, db_name):
    """Create database if it doesn't exist. Requires autocommit for CREATE DATABASE."""
    conn.autocommit = True
    cursor = conn.cursor()
    try:
        cursor.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(db_name)))
        print(f"Database '{db_name}' created successfully.")
    except errors.DuplicateDatabase:
        print(f"Database '{db_name}' already exists.")
    except psycopg2.Error as err:
        print(f"Failed creating database: {err}")
        exit(1)
    finally:
        cursor.close()
        conn.autocommit = False

try:
    # Connect to PostgreSQL server (to postgres database first for creating new db)
    cnx = psycopg2.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database="postgres"
    )
    print("Successfully connected to PostgreSQL server.")
    
    # Create the database
    create_database(cnx, DB_NAME)
    cnx.close()
    
    # Now connect to the target database
    cnx = psycopg2.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME
    )
    cursor = cnx.cursor()
    
except psycopg2.OperationalError as err:
    print(f"Connection error: {err}")
    exit(1)
except psycopg2.Error as err:
    print(err)
    exit(1)
else:
    print(f"Using database '{DB_NAME}'.")

# 2. Create Tables
TABLES = {}

TABLES['Table1'] = (
    "CREATE TABLE Table1 ("
    "  S_No INTEGER NOT NULL,"
    "  Import_Date DATE,"
    "  MIDA_NO VARCHAR(255),"
    "  Company_Name VARCHAR(255),"
    "  Declaration_Reg_No VARCHAR(255),"
    "  Kagayaku_Ref_No VARCHAR(255),"
    "  HsCode VARCHAR(255),"
    "  Item_Name VARCHAR(255),"
    "  Balance_Carried_Forward DECIMAL(10,2),"
    "  Quantity REAL,"
    "  Balance DECIMAL(10,2),"
    "  PRIMARY KEY (S_No)"
    ")")

TABLES['Table2'] = (
    "CREATE TABLE Table2 ("
    "  S_No INTEGER NOT NULL,"
    "  MIDA_NO VARCHAR(255),"
    "  Company_Name VARCHAR(255),"
    "  HsCode VARCHAR(255),"
    "  Item_Name VARCHAR(255),"
    "  Approved_Quantity DECIMAL(10,2),"
    "  Remaining_Quantity DECIMAL(10,2),"
    "  Date_of_exempt DATE,"
    "  Exemption_start_date DATE,"
    "  Exemption_end_date DATE,"
    "  PRIMARY KEY (S_No)"
    ")")

for table_name in TABLES:
    table_description = TABLES[table_name]
    try:
        print(f"Creating table {table_name}: ", end='')
        cursor.execute(table_description)
        cnx.commit()
    except errors.DuplicateTable:
        print("already exists.")
        cnx.rollback()
    except psycopg2.Error as err:
        print(err)
        cnx.rollback()
    else:
        print("OK")

## 3. Flexible Table Creation (for future use)
def generate_flexible_sql_script(table1_name, table2_name, quantity_data_type, metadata_fields):
    # Note: PostgreSQL uses \c or connection parameter to switch databases, not USE
    script = f"""
-- Connect to kagayaku_db database before running this script
-- \c kagayaku_db

CREATE TABLE IF NOT EXISTS {table1_name} (
    S_No INTEGER PRIMARY KEY,
    Import_Date DATE,
    MIDA_NO VARCHAR(255),
    Company_Name VARCHAR(255),
    Declaration_Reg_No VARCHAR(255),
    Kagayaku_Ref_No VARCHAR(255),
    HsCode VARCHAR(255),
    Item_Name VARCHAR(255),
    Balance_Carried_Forward DECIMAL(10, 2),
    Quantity {quantity_data_type},
    Balance DECIMAL(10, 2)
);

CREATE TABLE IF NOT EXISTS {table2_name} (
    S_No INTEGER PRIMARY KEY,
    MIDA_NO VARCHAR(255),
    Company_Name VARCHAR(255),
    HsCode VARCHAR(255),
    Item_Name VARCHAR(255),
    Approved_Quantity DECIMAL(10, 2),
    Remaining_Quantity DECIMAL(10, 2),
"""

    for field_name, field_type in metadata_fields.items():
        script += f"    {field_name} {field_type},\n"

    script = script.rstrip(",\n") + "\n);"
    return script

# Close connections
if 'cursor' in locals() and cursor:
    cursor.close()
if 'cnx' in locals() and cnx:
    cnx.close()
