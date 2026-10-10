from __future__ import annotations

import sqlite3
import hashlib
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import List, Dict

from app.models.transaction import Transaction
from app.services.categorizer import categorize


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "finance.db"


class DatabaseService:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        print(f"[DB DEBUG] DatabaseService initialized with DB path: {self.db_path}")
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                merchant TEXT,
                category TEXT,
                amount REAL,
                source_file TEXT,
                imported_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS imported_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                filepath TEXT,
                filesize INTEGER,
                filehash TEXT UNIQUE,
                imported_at TEXT
            )
            """
        )
        self._conn.commit()

    def insert_transactions(self, txs: List[Transaction], source_file: str) -> int:
        if not txs:
            return 0
        now = datetime.utcnow().isoformat()
        rows = []
        for tx in txs:
            if isinstance(tx.date, date):
                date_str = tx.date.isoformat()
            else:
                date_str = str(tx.date)
            merchant = tx.merchant_original
            # store an initial category based on current categorizer
            try:
                category = categorize(merchant)
            except Exception:
                category = None
            amount = float(tx.amount) if isinstance(tx.amount, (Decimal,)) else float(tx.amount)
            rows.append((date_str, merchant, category, amount, source_file, now))

        cur = self._conn.cursor()
        cur.executemany(
            "INSERT INTO transactions (date, merchant, category, amount, source_file, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        inserted = cur.rowcount
        print(f"[DB DEBUG] insert_transactions -> prepared {len(rows)} rows, inserted: {inserted}")
        return inserted

    def load_all_transactions(self, sort_column: str = "date", sort_direction: str = "DESC") -> List[Dict]:
        order_columns = {
            "date": "date",
            "merchant": "merchant COLLATE NOCASE",
            "category": "category COLLATE NOCASE",
            "amount": "amount",
        }
        if sort_column not in order_columns:
            raise ValueError(f"Unsupported transaction sort column: {sort_column}")

        direction = sort_direction.upper()
        if direction not in {"ASC", "DESC"}:
            raise ValueError(f"Unsupported transaction sort direction: {sort_direction}")

        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, date, merchant, category, amount, source_file, imported_at "
            f"FROM transactions ORDER BY {order_columns[sort_column]} {direction}, id ASC"
        )
        results = []
        for row in cur.fetchall():
            results.append({
                "id": row["id"],
                "date": row["date"],
                "merchant": row["merchant"],
                "category": row["category"],
                "amount": row["amount"],
                "source_file": row["source_file"],
                "imported_at": row["imported_at"],
            })
        return results

    def count_transactions(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions")
        return int(cur.fetchone()[0])

    def compute_file_hash(self, path: str | Path) -> str:
        path = Path(path)
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                h.update(chunk)
        filehash = h.hexdigest()
        print(f"[DB DEBUG] compute_file_hash -> {filehash}")
        return filehash

    def is_file_imported(self, filehash: str) -> bool:
        cur = self._conn.cursor()
        # exact query requested by debug spec
        q_filehash = "SELECT filehash FROM imported_files WHERE filehash = ?"
        cur.execute(q_filehash, (filehash,))
        fh_row = cur.fetchone()
        print(f"[DB DEBUG] is_file_imported - {q_filehash} params: ({filehash},) -> result: {fh_row}")

        # full row for context
        query = "SELECT id, filename, filepath, filesize, filehash, imported_at FROM imported_files WHERE filehash = ? LIMIT 1"
        cur.execute(query, (filehash,))
        row = cur.fetchone()
        print(f"[DB DEBUG] is_file_imported - full row query: {query} params: ({filehash},) -> row: {row}")
        return row is not None

    def add_imported_file(self, filename: str, filepath: str, filesize: int, filehash: str) -> int:
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        try:
            cur.execute(
                "INSERT INTO imported_files (filename, filepath, filesize, filehash, imported_at) VALUES (?, ?, ?, ?, ?)",
                (filename, filepath, filesize, filehash, now),
            )
            self._conn.commit()
            last_id = int(cur.lastrowid)
            print(f"[DB DEBUG] add_imported_file -> inserted id: {last_id}, filehash: {filehash}")
            return last_id
        except sqlite3.IntegrityError:
            return 0

    def get_imported_file_count(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM imported_files")
        return int(cur.fetchone()[0])

    def get_imported_file(self, filehash: str) -> Dict | None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, filename, filepath, filesize, filehash, imported_at FROM imported_files WHERE filehash = ? LIMIT 1",
            (filehash,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "filename": row["filename"],
            "filepath": row["filepath"],
            "filesize": row["filesize"],
            "filehash": row["filehash"],
            "imported_at": row["imported_at"],
        }
