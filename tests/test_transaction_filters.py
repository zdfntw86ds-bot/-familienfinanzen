import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from app.services.database_service import DatabaseService
from app.ui.main_window import MainWindow


class TransactionFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = DatabaseService(Path(self.temp_dir.name) / "transactions.db")
        self.database._conn.executemany(
            "INSERT INTO transactions (date, merchant, category, amount) VALUES (?, ?, ?, ?)",
            [
                ("2026-06-05", "Coop Bern", "Lebensmittel", -50.0),
                ("2026-06-28", "Coop Basel", "LEBENSMITTEL", -125.0),
                ("2026-07-02", "Coop Bern", "Lebensmittel", -75.0),
                ("2026-06-01", "Migros Bern", "Lebensmittel", -20.0),
                ("2026-06-20", "Unknown bonus", "Unbekannt", 150.0),
                ("2026-06-22", "No category", None, 40.0),
                ("2025-06-12", "Restaurant", "Essen", -30.0),
                ("2026-06-16", "Mensa", "Essen", -60.0),
                ("2026-06-18", "Bus", "ÖV", -12.0),
                ("2026-06-01", "Boundary start", "Misc", -20.0),
                ("2026-06-30", "Boundary end", "Misc", -100.0),
            ],
        )
        self.database._conn.commit()
        self.window = None

    def tearDown(self):
        if self.window:
            self.window.close()
        self.database._conn.close()
        self.temp_dir.cleanup()

    def _create_window(self):
        with (
            patch("app.ui.main_window.DatabaseService", return_value=self.database),
            patch("app.ui.main_window.FolderSyncService"),
            patch("app.ui.main_window.load_settings", return_value={}),
        ):
            self.window = MainWindow()

    def test_date_and_amount_ranges_are_inclusive(self):
        rows = self.database.load_all_transactions(
            date_from="2026-06-01",
            date_to="2026-06-30",
            min_amount=-100.0,
            max_amount=-20.0,
        )
        self.assertEqual(
            {row["merchant"] for row in rows},
            {"Coop Bern", "Migros Bern", "Mensa", "Boundary start", "Boundary end"},
        )

    def test_category_filter_is_casefolded_and_includes_unknown_rows(self):
        groceries = self.database.load_all_transactions(category="lebensmittel")
        self.assertEqual(
            {row["merchant"] for row in groceries},
            {"Coop Bern", "Coop Basel", "Migros Bern"},
        )

        unknown = self.database.load_all_transactions(category="UNBEKANNT", min_amount=100.0)
        self.assertEqual([row["merchant"] for row in unknown], ["Unknown bonus"])
        self.assertEqual(
            [row["merchant"] for row in self.database.load_all_transactions(category="öv")],
            ["Bus"],
        )

    def test_categories_are_loaded_from_stored_transactions(self):
        categories = self.database.load_transaction_categories()
        self.assertIn("Lebensmittel", categories)
        self.assertIn("ÖV", categories)
        self.assertIn("Unbekannt", categories)

    def test_search_and_filters_compose_and_sort_in_sqlite(self):
        rows = self.database.load_all_transactions(
            sort_column="amount",
            sort_direction="ASC",
            search_term="coop",
            date_from="2026-06-01",
            date_to="2026-06-30",
            category="Lebensmittel",
            min_amount=-100.0,
            max_amount=-20.0,
        )
        self.assertEqual([row["merchant"] for row in rows], ["Coop Bern"])

        sorted_rows = self.database.load_all_transactions(
            sort_column="amount",
            sort_direction="ASC",
            date_from="2026-06-01",
            date_to="2026-06-30",
            category="Lebensmittel",
            min_amount=-130.0,
            max_amount=-20.0,
        )
        self.assertEqual(
            [row["amount"] for row in sorted_rows],
            [-125.0, -50.0, -20.0],
        )

    def test_date_presets_calculate_expected_period_boundaries(self):
        self._create_window()
        today = QDate.currentDate()
        current_month_start = QDate(today.year(), today.month(), 1)
        previous_month_end = current_month_start.addDays(-1)
        expected = {
            0: {},
            1: {
                "date_from": current_month_start.toString("yyyy-MM-dd"),
                "date_to": current_month_start.addMonths(1).addDays(-1).toString("yyyy-MM-dd"),
            },
            2: {
                "date_from": QDate(previous_month_end.year(), previous_month_end.month(), 1).toString("yyyy-MM-dd"),
                "date_to": previous_month_end.toString("yyyy-MM-dd"),
            },
            3: {
                "date_from": QDate(today.year(), 1, 1).toString("yyyy-MM-dd"),
                "date_to": QDate(today.year(), 12, 31).toString("yyyy-MM-dd"),
            },
        }
        for index, filters in expected.items():
            with self.subTest(date_filter=index):
                self.window.date_filter.setCurrentIndex(index)
                self.assertEqual(self.window._transaction_filter_values(), filters)

    def test_ui_custom_filters_search_sort_and_reset(self):
        self._create_window()
        self.assertGreaterEqual(
            self.window.category_filter.findData("Lebensmittel"),
            0,
        )
        self.assertGreaterEqual(self.window.category_filter.findData("Unbekannt"), 0)

        self.window.date_filter.setCurrentIndex(4)
        self.window.date_from_filter.setDate(QDate(2026, 6, 1))
        self.window.date_to_filter.setDate(QDate(2026, 6, 30))
        self.window.category_filter.setCurrentIndex(
            self.window.category_filter.findData("Lebensmittel")
        )
        self.window.min_amount_filter.setText("-100")
        self.window.max_amount_filter.setText("-20")
        self.window.search_field.setText("coop")
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertEqual(self.window.table.item(0, 1).text(), "Coop Bern")

        self.window.search_field.clear()
        self.window.min_amount_filter.setText("-130")
        self.window.table.horizontalHeader().sectionClicked.emit(3)
        self.assertEqual(self.window.table.rowCount(), 3)
        self.assertEqual(
            [self.window.table.item(row, 1).text() for row in range(3)],
            ["Coop Basel", "Coop Bern", "Migros Bern"],
        )

        self.window.reset_filters_button.click()
        self.assertEqual(self.window.table.rowCount(), 11)
        self.assertEqual(self.window.search_field.text(), "")
        self.assertEqual(self.window.date_filter.currentIndex(), 0)
        self.assertEqual(self.window.category_filter.currentIndex(), 0)
        self.assertEqual(self.window.min_amount_filter.text(), "")
        self.assertEqual(self.window.max_amount_filter.text(), "")


if __name__ == "__main__":
    unittest.main()