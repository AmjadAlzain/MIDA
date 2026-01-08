"""Test UOM lookup for HS codes from sample invoice."""
import sys
import os
sys.path.insert(0, 'c:/Users/user/Desktop/AgentT/server')
os.chdir('c:/Users/user/Desktop/AgentT/server')

# Need to load .env for database URL
from dotenv import load_dotenv
load_dotenv()

from app.db.session import get_session_factory
from app.repositories.hscode_uom_repo import get_uom_by_hscode, HscodeNotFoundError

SessionLocal = get_session_factory()
if SessionLocal is None:
    print("Database not configured. Check DATABASE_URL in .env")
    sys.exit(1)

# HS codes from sample invoice.csv
test_codes = [
    "84099139",  # Line 1
    "84849000",  # Line 2
    "87141090",  # Line 5
    "84836000",  # Line 10
    "84099132",  # Line 12
    "73181590",  # Line 13
    "84834090",  # Line 24
]

db = SessionLocal()
try:
    for code in test_codes:
        try:
            uom = get_uom_by_hscode(db, code)
            print(f"HSCODE '{code}' -> UOM: '{uom}'")
        except HscodeNotFoundError as e:
            print(f"HSCODE '{code}' -> NOT FOUND")
finally:
    db.close()
