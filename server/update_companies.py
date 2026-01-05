"""Update company names in the database."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import get_session_factory
from sqlalchemy import text

session_factory = get_session_factory()
db = session_factory()
try:
    db.execute(text("UPDATE companies SET name = 'HICOM YAMAHA MOTOR SDN BHD' WHERE name = 'HICOM'"))
    db.execute(text("UPDATE companies SET name = 'HONG LEONG YAMAHA MOTOR SDN BHD' WHERE name = 'Hong Leong'"))
    db.commit()
    print('Companies updated successfully!')
    
    # Verify
    result = db.execute(text('SELECT name FROM companies')).fetchall()
    for row in result:
        print(f'  - {row[0]}')
except Exception as e:
    print(f'Error: {e}')
finally:
    db.close()
