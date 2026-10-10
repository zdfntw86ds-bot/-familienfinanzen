import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.services.database_service import DatabaseService
from app.ui.main_window import MainWindow


class TransactionSortingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = DatabaseService(Path(self.temp_dir.name) / "transactions.db")
        self.database._conn.executemany(
            "INSERT INTO transactions (date, merchant, category, amount) VALUES (?, ?, ?, ?)",
            [
                ("2024-12-01", "Beta", "Travel", 100.0),
                ("2025-02-10", "alpha", "Food", 9.0),
                ("2025-01-05", "Gamma", "Food", 20.0),
            ],
        )
        self.database._conn.commit()

    def tearDown(self):
        self.database._conn.close()
        self.temp_dir.cleanup()

    def test_default_is_date_descending(self):
        rows = self.database.load_all_transactions()
        self.assertEqual([row["date"] for row in rows], ["2025-02-10", "2025-01-05", "2024-12-01"])

    def test_all_supported_columns_sort_ascending_and_descending(self):
        cases = {
            "date": (["2024-12-01", "2025-01-05", "2025-02-10"], ["2025-02-10", "2025-01-05", "2024-12-01"]),
            "merchant": (["alpha", "Beta", "Gamma"], ["Gamma", "Beta", "alpha"]),
            "category": (["Food", "Food", "Travel"], ["Travel", "Food", "Food"]),
            "amount": ([9.0, 20.0, 100.0], [100.0, 20.0, 9.0]),
        }
        value_keys = {"date": "date", "merchant": "merchant", "category": "category", "amount": "amount"}

        for column, (ascending, descending) in cases.items():
            with self.subTest(column=column, direction="ASC"):
                rows = self.database.load_all_transactions(column, "ASC")
                self.assertEqual([row[value_keys[column]] for row in rows], ascending)
            with self.subTest(column=column, direction="DESC"):
                rows = self.database.load_all_transactions(column, "DESC")
                self.assertEqual([row[value_keys[column]] for row in rows], descending)

    def test_rejects_unsupported_sort_values(self):
        with self.assertRaises(ValueError):
            self.database.load_all_transactions("id; DROP TABLE transactions", "ASC")
        with self.assertRaises(ValueError):
            self.database.load_all_transactions("date", "sideways")

    def test_header_toggles_and_sync_reload_preserves_sort(self):
        QApplication.instance() or QApplication([])
        self.database.load_all_transactions = Mock(wraps=self.database.load_all_transactions)
        sync_service = Mock()
        sync_service.sync.return_value = {
            "scanned_pdfs": 0,
            "new_imports": 0,
            "already_imported": 0,
            "unknown": 0,
            "transactions_imported": 0,
        }

        with (
            patch("app.ui.main_window.DatabaseService", return_value=self.database),
            patch("app.ui.main_window.FolderSyncService", return_value=sync_service),
            patch("app.ui.main_window.load_settings", return_value={"finance_folder": "/finance"}),
            patch.object(QMessageBox, "information"),
        ):
            window = MainWindow()
            header = window.table.horizontalHeader()
            cases = {
                0: ("date", "01.12.2024", "10.02.2025"),
                1: ("merchant", "alpha", "Gamma"),
                2: ("category", "Food", "Travel"),
                3: ("amount", "9.00", "100.00"),
            }
            for column, (sort_column, ascending_first, descending_first) in cases.items():
                header.sectionClicked.emit(column)
                self.assertEqual((window._sort_column, window._sort_direction), (sort_column, "ASC"))
                first_cell = window.table.item(0, column)
                self.assertEqual(first_cell.text(), ascending_first)

                header.sectionClicked.emit(column)
                self.assertEqual((window._sort_column, window._sort_direction), (sort_column, "DESC"))
                first_cell = window.table.item(0, column)
                self.assertEqual(first_cell.text(), descending_first)

            window._synchronize_folder()

        self.assertEqual(self.database.load_all_transactions.call_args, call("amount", "DESC"))
        self.assertEqual(window.table.item(0, 3).text(), "100.00")
        window.close()


if __name__ == "__main__":
    unittest.main()