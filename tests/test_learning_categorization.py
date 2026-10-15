import os
import sqlite3
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.models.transaction import Transaction
from app.services.categorizer import categorize
from app.services.database_service import DatabaseService
from app.ui.main_window import MainWindow


class LearningCategorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "transactions.db"
        self.database = DatabaseService(self.database_path)

    def tearDown(self):
        self.database._conn.close()
        self.temp_dir.cleanup()

    @staticmethod
    def _transaction(merchant, category=None):
        return Transaction(
            date=date(2026, 6, 1),
            merchant_original=merchant,
            amount=Decimal("12.50"),
            category=category,
        )

    def _categories_by_merchant(self):
        return {
            row["merchant"]: row["category"]
            for row in self.database.load_all_transactions()
        }

    def test_existing_keyword_rules_categorize_known_merchants(self):
        with patch("app.services.categorizer.get_user_category", return_value=None):
            self.assertEqual(categorize("COOP-1931 ZOLLIKOFEN"), "Lebensmittel")
            self.assertEqual(categorize("MIGROS BERN"), "Lebensmittel")
            self.assertEqual(categorize("NETFLIX"), "Unbekannt")

    def test_import_applies_learned_rule_and_preserves_explicit_category(self):
        self.database.save_merchant_category_rule("Stream Shop", "Abonnements")
        transactions = [
            self._transaction("Stream Shop"),
            self._transaction("Unknown Merchant"),
            self._transaction("Stream Shop", "Wohnen"),
        ]
        with patch(
            "app.services.database_service.categorize",
            side_effect=lambda merchant: "Unbekannt",
        ):
            self.database.insert_transactions(transactions, "viseca_statement.pdf")

        rows = self.database._conn.execute(
            "SELECT merchant, category FROM transactions ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [(row["merchant"], row["category"]) for row in rows],
            [
                ("Stream Shop", "Abonnements"),
                ("Unknown Merchant", None),
                ("Stream Shop", "Wohnen"),
            ],
        )

    def test_learned_rule_is_case_insensitive_and_persists_after_restart(self):
        self.database.save_merchant_category_rule("VeloShop XY", "Mobilität / Velo")
        self.database._conn.close()
        self.database = DatabaseService(self.database_path)

        with patch("app.services.database_service.categorize", return_value="Unbekannt"):
            self.database.insert_transactions(
                [self._transaction("veloshop xy")],
                "postfinance_statement.pdf",
            )

        self.assertEqual(self._categories_by_merchant()["veloshop xy"], "Mobilität / Velo")

    def test_duplicate_rule_is_idempotent_and_conflicts_require_override(self):
        self.assertTrue(self.database.save_merchant_category_rule("Coop Bern", "Lebensmittel"))
        self.assertFalse(self.database.save_merchant_category_rule("COOP BERN", "Lebensmittel"))
        with self.assertRaises(ValueError):
            self.database.save_merchant_category_rule("Coop Bern", "Wohnen")

        self.database.save_merchant_category_rule(
            "Coop Bern",
            "Wohnen",
            replace_existing=True,
        )
        self.assertEqual(self.database.get_merchant_category_rule("coop bern"), "Wohnen")
        self.assertEqual(
            self.database._conn.execute(
                "SELECT COUNT(*) FROM merchant_category_rules"
            ).fetchone()[0],
            1,
        )

    def test_category_rule_management_updates_and_removes_learned_rules(self):
        self.database.save_merchant_category_rule("Home Store", "Wohnen")
        self.assertEqual(self.database.update_merchant_category_rules("Wohnen", "Haushalt"), 1)
        self.assertEqual(self.database.get_merchant_category_rule("Home Store"), "Haushalt")
        self.assertEqual(self.database.update_merchant_category_rules("Haushalt", None), 1)
        self.assertIsNone(self.database.get_merchant_category_rule("Home Store"))

    def test_existing_all_future_action_persists_sqlite_rule(self):
        with (
            patch("app.ui.main_window.DatabaseService", return_value=self.database),
            patch("app.ui.main_window.FolderSyncService"),
            patch("app.ui.main_window.load_settings", return_value={}),
            patch("app.ui.main_window.set_user_category") as save_legacy_rule,
            patch.object(QMessageBox, "information"),
        ):
            window = MainWindow()
            window._apply_category_change(0, "Stream Shop", "Abonnements", True)
            window.close()

        self.assertEqual(
            self.database.get_merchant_category_rule("stream shop"),
            "Abonnements",
        )
        save_legacy_rule.assert_called_once_with("Stream Shop", "Abonnements")

    def test_existing_database_data_survives_repeatable_schema_upgrade(self):
        self.database._conn.close()
        self.database_path.unlink()
        connection = sqlite3.connect(self.database_path)
        connection.execute(
            "CREATE TABLE transactions (id INTEGER PRIMARY KEY, date TEXT, merchant TEXT, "
            "category TEXT, amount REAL, source_file TEXT, imported_at TEXT)"
        )
        connection.execute(
            "CREATE TABLE imported_files (id INTEGER PRIMARY KEY, filename TEXT, filepath TEXT, "
            "filesize INTEGER, filehash TEXT UNIQUE, imported_at TEXT)"
        )
        connection.execute(
            "INSERT INTO transactions VALUES (1, '2025-01-01', 'Existing', 'Wohnen', 10, 'old.pdf', 'now')"
        )
        connection.commit()
        connection.close()

        self.database = DatabaseService(self.database_path)
        self.assertEqual(self.database.count_transactions(), 1)
        self.assertEqual(self.database.load_all_transactions()[0]["merchant"], "Existing")
        self.database._conn.close()
        self.database = DatabaseService(self.database_path)
        tables = {
            row[0]
            for row in self.database._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertIn("merchant_category_rules", tables)
        self.assertEqual(self.database.count_transactions(), 1)


if __name__ == "__main__":
    unittest.main()