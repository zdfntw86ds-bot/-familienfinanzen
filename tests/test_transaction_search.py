import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.services.database_service import DatabaseService
from app.ui.main_window import MainWindow


class TransactionSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = DatabaseService(Path(self.temp_dir.name) / "transactions.db")
        self.database._conn.executemany(
            "INSERT INTO transactions (date, merchant, category, amount) VALUES (?, ?, ?, ?)",
            [
                ("2025-03-01", "Coop Bern", "Groceries", -25.0),
                ("2025-03-02", "Migros Bern", "Groceries", -18.0),
                ("2025-03-03", "TWINT Coffee Shop", "Dining", -7.5),
                ("2025-03-04", "Salary ACME", "Income", 5000.0),
            ],
        )
        self.database._conn.commit()

    def tearDown(self):
        self.database._conn.close()
        self.temp_dir.cleanup()

    def test_search_matches_merchant_and_category_case_insensitively(self):
        self.assertEqual(
            [row["merchant"] for row in self.database.load_all_transactions(search_term="coop")],
            ["Coop Bern"],
        )
        self.assertEqual(
            [row["merchant"] for row in self.database.load_all_transactions(search_term="bern")],
            ["Migros Bern", "Coop Bern"],
        )
        self.assertEqual(
            [row["merchant"] for row in self.database.load_all_transactions(search_term="gRoCeRiEs")],
            ["Migros Bern", "Coop Bern"],
        )

    def test_search_supports_partial_matches_and_literal_like_characters(self):
        self.assertEqual(
            [row["merchant"] for row in self.database.load_all_transactions(search_term="wint cof")],
            ["TWINT Coffee Shop"],
        )
        self.assertEqual(self.database.load_all_transactions(search_term="%"), [])
        self.assertEqual(self.database.load_all_transactions(search_term="_"), [])

    def test_empty_search_restores_all_rows(self):
        self.assertEqual(len(self.database.load_all_transactions(search_term="bern")), 2)
        self.assertEqual(len(self.database.load_all_transactions(search_term="")), 4)

    def test_live_search_preserves_sort_and_clearing_restores_rows(self):
        QApplication.instance() or QApplication([])
        self.database.load_all_transactions = Mock(wraps=self.database.load_all_transactions)

        with (
            patch("app.ui.main_window.DatabaseService", return_value=self.database),
            patch("app.ui.main_window.FolderSyncService"),
            patch("app.ui.main_window.load_settings", return_value={}),
        ):
            window = MainWindow()
            window.table.horizontalHeader().sectionClicked.emit(1)
            window.table.horizontalHeader().sectionClicked.emit(1)
            self.assertEqual((window._sort_column, window._sort_direction), ("merchant", "DESC"))

            window.search_field.setText("bern")
            self.assertEqual(window.table.rowCount(), 2)
            self.assertEqual(window.table.item(0, 1).text(), "Migros Bern")
            self.assertEqual(
                self.database.load_all_transactions.call_args.args,
                ("merchant", "DESC", "bern"),
            )

            window.search_field.clear()
            self.assertEqual(window.table.rowCount(), 4)
            self.assertEqual(
                self.database.load_all_transactions.call_args.args,
                ("merchant", "DESC", ""),
            )
            window.close()


if __name__ == "__main__":
    unittest.main()