from pathlib import Path
import sys
# ensure project root is on sys.path so 'app' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from decimal import Decimal
from datetime import date

from app.services.database_service import DatabaseService
from app.models.transaction import Transaction

print('Starting debug_import script')

db = DatabaseService()

p = Path('data/test_sample.pdf')
p.parent.mkdir(parents=True, exist_ok=True)
# create or overwrite a sample file
p.write_bytes(b'This is a test PDF-like content')

print(f"Test file created at: {p.resolve()}")

# Step 1: compute hash
filehash = db.compute_file_hash(p)
print(f"[SCRIPT] computed hash: {filehash}")

# Step 2: check is_file_imported
imported_before = db.is_file_imported(filehash)
print(f"[SCRIPT] is_file_imported before adding: {imported_before}")

# Prepare a transaction and insert
tx = Transaction(date=date.today(), merchant_original='Test Merchant', amount=Decimal('10.00'))
inserted = db.insert_transactions([tx], p.name)
print(f"[SCRIPT] insert_transactions returned: {inserted}")

# Add imported file record
added = db.add_imported_file(p.name, str(p.resolve()), p.stat().st_size, filehash)
print(f"[SCRIPT] add_imported_file returned: {added}")

# Check is_file_imported again
imported_after = db.is_file_imported(filehash)
print(f"[SCRIPT] is_file_imported after adding: {imported_after}")

# Attempt second import simulation
filehash2 = db.compute_file_hash(p)
print(f"[SCRIPT] computed second hash: {filehash2}")
imported_second = db.is_file_imported(filehash2)
print(f"[SCRIPT] is_file_imported on second attempt: {imported_second}")

inserted2 = db.insert_transactions([tx], p.name)
print(f"[SCRIPT] insert_transactions second attempt returned: {inserted2}")

added2 = db.add_imported_file(p.name, str(p.resolve()), p.stat().st_size, filehash2)
print(f"[SCRIPT] add_imported_file second attempt returned: {added2}")

print('Done')
