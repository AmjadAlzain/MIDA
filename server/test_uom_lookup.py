"""Quick test to verify UOM lookup is working."""
import sys
sys.path.insert(0, '.')

from app.db.session import get_session_factory
from app.repositories.hscode_uom_repo import get_uom_by_hscode, HscodeNotFoundError

# Get session factory
SessionLocal = get_session_factory()

# Test cases
test_codes = [
    "79100100",
    "7910010000",
    "87149100",
    "8714910000",
]

db = SessionLocal()
try:
    for code in test_codes:
        try:
            uom = get_uom_by_hscode(db, code)
            print(f"HSCODE '{code}' -> UOM: '{uom}' (type: {type(uom).__name__})")
        except HscodeNotFoundError as e:
            print(f"HSCODE '{code}' -> NOT FOUND: {e}")
finally:
    db.close()
