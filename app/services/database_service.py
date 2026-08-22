from __future__ import annotations

import sqlite3
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
        return cur.rowcount

    def load_all_transactions(self) -> List[Dict]:
        cur = self._conn.cursor()
        cur.execute("SELECT id, date, merchant, category, amount, source_file, imported_at FROM transactions ORDER BY id ASC")
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
