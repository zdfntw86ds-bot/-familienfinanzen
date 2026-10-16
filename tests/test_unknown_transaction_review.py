import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QComboBox

from app.models.transaction import Transaction
from app.services.database_service import DatabaseService
from app.ui.main_window import MainWindow
from app.ui.unknown_transaction_review_dialog import UnknownTransactionReviewDialog


class UnknownTransactionReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "transactions.db"
        self.database = DatabaseService(self.database_path)
        self.database._conn.executemany(
            "INSERT INTO transactions (date, merchant, category, amount) VALUES (?, ?, ?, ?)",
            [
                ("2026-10-03", "Unknown Shop", None, 25.0),
                ("2026-10-01", "Another Shop", "Unbekannt", -5.0),
                ("2026-10-02", "Blank Shop", "  ", 12.0),
                ("2026-10-04", "Known Shop", "Essen", 8.0),
            ],
        )
        self.database._conn.commit()
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()
        self.database._conn.close()
        self.temp_dir.cleanup()

    def _dialog(self, category_creator=lambda: None):
        dialog = UnknownTransactionReviewDialog(self.database, category_creator)
        self.dialogs.append(dialog)
        return dialog

    def _record_by_merchant(self, merchant):
        return next(
            row for row in self.database.load_unknown_transactions()
            if row["merchant"] == merchant
        )

    def _combo_for_row(self, dialog, row):
        return dialog.table.cellWidget(row, 3)

    def test_unknown_detection_includes_null_blank_and_unknown_and_supports_sorting(self):
        self.assertEqual(self.database.count_unknown_transactions(), 3)
        self.assertEqual(
            [row["merchant"] for row in self.database.load_unknown_transactions("date", "ASC")],
            ["Another Shop", "Blank Shop", "Unknown Shop"],
        )
        self.assertEqual(
            [row["merchant"] for row in self.database.load_unknown_transactions("amount", "ASC")],
            ["Another Shop", "Blank Shop", "Unknown Shop"],
        )
        self.assertEqual(
            [row["merchant"] for row in self.database.load_unknown_transactions("merchant", "ASC")],
            ["Another Shop", "Blank Shop", "Unknown Shop"],
        )
        with self.assertRaises(ValueError):
            self.database.load_unknown_transactions("category")

    def test_category_creation_is_persisted_and_case_insensitive(self):
        self.assertEqual(self.database.add_category("  Abonnements "), "Abonnements")
        self.assertEqual(self.database.add_category("abonnements"), "Abonnements")
        self.assertEqual(
            sum(name.casefold() == "abonnements" for name in self.database.load_categories()),
            1,
        )

    def test_dialog_loads_rows_and_individual_category_assignment(self):
        dialog = self._dialog()
        self.assertEqual(dialog.table.rowCount(), 3)
        self.assertIn("Zu prüfen: 3", dialog.total_label.text())
        self.assertIn("Noch nicht kategorisiert: 3", dialog.uncategorized_label.text())

        row = next(
            index for index in range(dialog.table.rowCount())
            if dialog.table.item(index, 1).text() == "Unknown Shop"
        )
        combo = self._combo_for_row(dialog, row)
        combo.setCurrentIndex(combo.findData("Lebensmittel"))
        self.assertEqual(dialog._categories[self._record_by_merchant("Unknown Shop")["id"]], "Lebensmittel")
        self.assertIn("Noch nicht kategorisiert: 2", dialog.uncategorized_label.text())

    def test_batch_assignment_changes_only_selected_rows(self):
        dialog = self._dialog()
        dialog.batch_category.setCurrentIndex(dialog.batch_category.findData("Reisen"))
        for row in (0, 1):
            dialog.table.selectionModel().select(
                dialog.table.model().index(row, 0),
                QItemSelectionModel.Select | QItemSelectionModel.Rows,
            )
        dialog._apply_to_selection()

        assigned_ids = {
            dialog.table.item(row, 0).data(Qt.UserRole)
            for row in range(dialog.table.rowCount())
            if dialog._categories[dialog.table.item(row, 0).data(Qt.UserRole)] == "Reisen"
        }
        self.assertEqual(len(assigned_ids), 2)
        self.assertEqual(sum(value is None for value in dialog._categories.values()), 1)

    def test_new_category_is_immediately_available_in_all_dropdowns(self):
        dialog = self._dialog(category_creator=lambda: "Abonnements")
        dialog.new_category_button.click()
        self.assertIn("Abonnements", self.database.load_categories())
        self.assertGreaterEqual(dialog.batch_category.findData("Abonnements"), 0)
        for row in range(dialog.table.rowCount()):
            self.assertGreaterEqual(self._combo_for_row(dialog, row).findData("Abonnements"), 0)

    def test_save_persists_multiple_assignments_and_leaves_uncategorized_rows(self):
        dialog = self._dialog()
        for row in range(dialog.table.rowCount()):
            merchant = dialog.table.item(row, 1).text()
            combo = self._combo_for_row(dialog, row)
            category = "Lebensmittel" if merchant == "Unknown Shop" else "Reisen"
            combo.setCurrentIndex(combo.findData(category))
        patcher = patch.object(dialog, "accept")
        with patcher:
            dialog._save()

        rows = {row["merchant"]: row["category"] for row in self.database.load_all_transactions()}
        self.assertEqual(rows["Unknown Shop"], "Lebensmittel")
        self.assertEqual(rows["Another Shop"], "Reisen")
        self.assertEqual(rows["Blank Shop"], "Reisen")
        self.assertEqual(rows["Known Shop"], "Essen")
        self.assertEqual(self.database.count_unknown_transactions(), 0)
        self.assertTrue(dialog.saved)

    def test_remembered_rule_is_saved_and_manual_assignment_does_not_create_rule(self):
        dialog = self._dialog()
        target_row = next(
            row for row in range(dialog.table.rowCount())
            if dialog.table.item(row, 1).text() == "Unknown Shop"
        )
        combo = self._combo_for_row(dialog, target_row)
        combo.setCurrentIndex(combo.findData("Technik"))
        dialog.table.item(target_row, 4).setCheckState(Qt.Checked)
        with patch.object(dialog, "accept"):
            dialog._save()
        self.assertEqual(self.database.get_merchant_category_rule("Unknown Shop"), "Technik")

        other = self._dialog()
        target_row = next(
            row for row in range(other.table.rowCount())
            if other.table.item(row, 1).text() == "Another Shop"
        )
        self._combo_for_row(other, target_row).setCurrentIndex(
            self._combo_for_row(other, target_row).findData("Wohnen")
        )
        with patch.object(other, "accept"):
            other._save()
        self.assertIsNone(self.database.get_merchant_category_rule("Another Shop"))

    def test_conflicting_remembered_rules_are_rejected_without_partial_save(self):
        self.database._conn.execute(
            "INSERT INTO transactions (date, merchant, category, amount) VALUES (?, ?, ?, ?)",
            ("2026-10-05", "Unknown Shop", None, 40.0),
        )
        self.database._conn.commit()
        dialog = self._dialog()
        rows = [
            row for row in range(dialog.table.rowCount())
            if dialog.table.item(row, 1).text() == "Unknown Shop"
        ]
        for row, category in zip(rows, ("Technik", "Wohnen")):
            combo = self._combo_for_row(dialog, row)
            combo.setCurrentIndex(combo.findData(category))
            dialog.table.item(row, 4).setCheckState(Qt.Checked)
        with patch.object(QMessageBox, "warning") as warning, patch.object(dialog, "accept"):
            dialog._save()
        warning.assert_called_once()
        self.assertIsNone(self.database.get_merchant_category_rule("Unknown Shop"))
        self.assertEqual(self.database.count_unknown_transactions(), 4)

    def test_existing_rule_conflict_requires_confirmation_and_decline_preserves_rule(self):
        self.database.save_merchant_category_rule("Unknown Shop", "Essen")
        dialog = self._dialog()
        row = next(
            index for index in range(dialog.table.rowCount())
            if dialog.table.item(index, 1).text() == "Unknown Shop"
        )
        combo = self._combo_for_row(dialog, row)
        combo.setCurrentIndex(combo.findData("Technik"))
        dialog.table.item(row, 4).setCheckState(Qt.Checked)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as question:
            with patch.object(dialog, "accept"):
                dialog._save()
        question.assert_called_once()
        self.assertEqual(self.database.get_merchant_category_rule("Unknown Shop"), "Essen")
        saved_row = next(
            row for row in self.database.load_all_transactions()
            if row["merchant"] == "Unknown Shop"
        )
        self.assertEqual(saved_row["category"], "Technik")

    def test_service_rule_conflict_rolls_back_all_category_changes(self):
        self.database.save_merchant_category_rule("Unknown Shop", "Essen")
        unknown_id = self._record_by_merchant("Unknown Shop")["id"]
        other_id = self._record_by_merchant("Another Shop")["id"]
        with self.assertRaises(ValueError):
            self.database.save_reviewed_transactions(
                {unknown_id: "Technik", other_id: "Wohnen"},
                [("Unknown Shop", "Technik")],
            )
        self.assertIsNone(self._record_by_merchant("Unknown Shop")["category"])
        self.assertEqual(self.database.get_merchant_category_rule("Unknown Shop"), "Essen")

    def test_remembered_rule_retroactively_updates_only_unknown_exact_merchant_matches(self):
        self.database._conn.executemany(
            "INSERT INTO transactions (date, merchant, category, amount, source_file) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("2026-10-11", " LANDI LADEN ZOLLIKOFEN ", None, 17.95, "old.pdf"),
                ("2026-10-12", "landi laden zollikofen", "Unbekannt", 5.20, "old.pdf"),
                ("2026-10-13", "LANDI LADEN ZOLLIKOFEN", "Garten", 9.10, "old.pdf"),
                ("2026-10-14", "LANDI LADEN BERN", None, 2.00, "old.pdf"),
            ],
        )
        self.database._conn.commit()
        target = next(
            row for row in self.database.load_all_transactions()
            if row["amount"] == 17.95
        )

        self.database.save_reviewed_transactions(
            {target["id"]: "NonFood divers"},
            [(" LANDI LADEN ZOLLIKOFEN ", "NonFood divers")],
        )

        categories_by_amount = {
            row["amount"]: row["category"]
            for row in self.database.load_all_transactions()
        }
        self.assertEqual(categories_by_amount[17.95], "NonFood divers")
        self.assertEqual(categories_by_amount[5.20], "NonFood divers")
        self.assertEqual(categories_by_amount[9.10], "Garten")
        self.assertIsNone(categories_by_amount[2.00])
        self.assertEqual(self.database.count_unknown_transactions(), 4)

    def test_rule_is_idempotent_persists_after_restart_and_categorizes_future_imports(self):
        self.database._conn.execute(
            "INSERT INTO transactions (date, merchant, category, amount) VALUES (?, ?, ?, ?)",
            ("2026-10-11", "LANDI LADEN ZOLLIKOFEN", None, 17.95),
        )
        self.database._conn.commit()
        target = next(
            row for row in self.database.load_unknown_transactions()
            if row["merchant"] == "LANDI LADEN ZOLLIKOFEN"
        )
        reviewed = {target["id"]: "NonFood divers"}
        rule = [("LANDI LADEN ZOLLIKOFEN", "NonFood divers")]
        self.database.save_reviewed_transactions(reviewed, rule)
        self.database.save_reviewed_transactions(reviewed, rule)
        self.assertEqual(
            self.database._conn.execute(
                "SELECT COUNT(*) FROM merchant_category_rules WHERE CASEFOLD(merchant) = CASEFOLD(?)",
                ("LANDI LADEN ZOLLIKOFEN",),
            ).fetchone()[0],
            1,
        )

        self.database._conn.close()
        self.database = DatabaseService(self.database_path)
        self.assertEqual(
            self.database.get_merchant_category_rule(" landi laden zollikofen "),
            "NonFood divers",
        )
        with patch("app.services.database_service.categorize", return_value="Unbekannt"):
            self.database.insert_transactions(
                [
                    Transaction(
                        date=date(2026, 10, 15),
                        merchant_original=" landi laden zollikofen ",
                        amount=Decimal("4.25"),
                    )
                ],
                "future.pdf",
            )
        future = next(
            row for row in self.database.load_all_transactions()
            if row["source_file"] == "future.pdf"
        )
        self.assertEqual(future["category"], "NonFood divers")

    def test_category_without_remembering_rule_only_updates_selected_transaction(self):
        self.database._conn.executemany(
            "INSERT INTO transactions (date, merchant, category, amount) VALUES (?, ?, ?, ?)",
            [
                ("2026-10-11", "LANDI LADEN ZOLLIKOFEN", None, 17.95),
                ("2026-10-12", "landi laden zollikofen", None, 5.20),
            ],
        )
        self.database._conn.commit()
        dialog = self._dialog()
        target_row = next(
            row for row in range(dialog.table.rowCount())
            if dialog.table.item(row, 2).text() == "17.95"
        )
        combo = self._combo_for_row(dialog, target_row)
        combo.setCurrentIndex(combo.findData("NonFood divers"))
        with patch.object(dialog, "accept"):
            dialog._save()

        categories_by_amount = {
            row["amount"]: row["category"]
            for row in self.database.load_all_transactions()
        }
        self.assertEqual(categories_by_amount[17.95], "NonFood divers")
        self.assertIsNone(categories_by_amount[5.20])
        self.assertIsNone(
            self.database.get_merchant_category_rule("LANDI LADEN ZOLLIKOFEN")
        )

    def test_review_save_refreshes_main_unknown_counter(self):
        window = self._main_window()
        target = self._record_by_merchant("Unknown Shop")

        class SavingDialog:
            saved = True

            def exec(self):
                self.database.save_reviewed_transactions(
                    {target["id"]: "Lebensmittel"}, []
                )

        def create_dialog(*_args, **_kwargs):
            dialog = SavingDialog()
            dialog.database = self.database
            return dialog

        with (
            patch("app.ui.main_window.UnknownTransactionReviewDialog", side_effect=create_dialog),
            patch("app.ui.main_window.QMessageBox.information"),
        ):
            window._open_unknown_review()
        self.assertEqual(window.unknown_transactions_button.text(), "Unbekannte Transaktionen (2)")
        window.close()

    def test_cancel_and_later_leave_transaction_and_rule_data_unchanged(self):
        dialog = self._dialog()
        row = 0
        combo = self._combo_for_row(dialog, row)
        combo.setCurrentIndex(combo.findData("Technik"))
        dialog.reject()
        self.assertEqual(self.database.count_unknown_transactions(), 3)
        self.assertIsNone(self.database.get_merchant_category_rule("Unknown Shop"))
        self.assertIsNone(self._record_by_merchant("Unknown Shop")["category"])

        later = self._dialog()
        self.assertEqual(later.done(2), None)
        self.assertEqual(self.database.count_unknown_transactions(), 3)

    def test_review_later_button_opens_the_same_dialog_without_saving(self):
        dialog = self._dialog()
        with patch.object(dialog, "done") as done:
            dialog.later_button.click()
        done.assert_called_once_with(2)
        self.assertEqual(self.database.count_unknown_transactions(), 3)

    def test_import_opens_review_when_new_unknown_transactions_are_inserted(self):
        window = self._main_window()
        pdf_path = Path(self.temp_dir.name) / "viseca_statement.pdf"
        pdf_path.write_bytes(b"test pdf")
        tx = Transaction(
            date=date(2026, 10, 8),
            merchant_original="Unknown Imported Shop",
            amount=Decimal("15.00"),
            category=None,
        )
        with (
            patch("app.ui.main_window.QFileDialog.getOpenFileName", return_value=(str(pdf_path), "PDF")),
            patch("app.ui.main_window.extract_text_from_pdf", return_value="statement"),
            patch("app.ui.main_window.parse_viseca_pdf", return_value=[tx]),
            patch.object(window, "_open_unknown_review") as open_review,
        ):
            window._import_pdf()
        open_review.assert_called_once()
        window.close()

    def test_postfinance_import_uses_the_unknown_review_workflow(self):
        window = self._main_window()
        pdf_path = Path(self.temp_dir.name) / "postfinance_statement.pdf"
        pdf_path.write_bytes(b"test postfinance pdf")
        tx = Transaction(
            date=date(2026, 10, 9),
            merchant_original="Postfinance Unknown Shop",
            amount=Decimal("18.00"),
            category=None,
        )
        with (
            patch("app.ui.main_window.QFileDialog.getOpenFileName", return_value=(str(pdf_path), "PDF")),
            patch("app.ui.main_window.extract_text_from_pdf", return_value="statement"),
            patch("app.ui.main_window.parse_postfinance_pdf", return_value=[tx]),
            patch.object(window, "_open_unknown_review") as open_review,
        ):
            window._import_pdf()
        open_review.assert_called_once()
        window.close()

    def test_import_skips_review_when_no_unknown_transactions_remain(self):
        self.database._conn.execute(
            "UPDATE transactions SET category = 'Essen' WHERE category IS NULL "
            "OR TRIM(category) = '' OR category = 'Unbekannt'"
        )
        self.database._conn.commit()
        window = self._main_window()
        pdf_path = Path(self.temp_dir.name) / "viseca_categorized.pdf"
        pdf_path.write_bytes(b"categorized pdf")
        tx = Transaction(
            date=date(2026, 10, 10),
            merchant_original="Known Imported Shop",
            amount=Decimal("18.00"),
            category="Wohnen",
        )
        with (
            patch("app.ui.main_window.QFileDialog.getOpenFileName", return_value=(str(pdf_path), "PDF")),
            patch("app.ui.main_window.extract_text_from_pdf", return_value="statement"),
            patch("app.ui.main_window.parse_viseca_pdf", return_value=[tx]),
            patch.object(window, "_open_unknown_review") as open_review,
        ):
            window._import_pdf()
        open_review.assert_not_called()
        window.close()

    def test_review_later_main_button_uses_shared_dialog_and_updates_unknown_count(self):
        window = self._main_window()
        with patch("app.ui.main_window.UnknownTransactionReviewDialog") as dialog_type:
            dialog_type.return_value.saved = False
            window._open_unknown_review()
        dialog_type.assert_called_once()
        self.assertEqual(window.unknown_transactions_button.text(), "Unbekannte Transaktionen (3)")
        window.close()

    def _main_window(self):
        with (
            patch("app.ui.main_window.DatabaseService", return_value=self.database),
            patch("app.ui.main_window.FolderSyncService"),
            patch("app.ui.main_window.load_settings", return_value={}),
        ):
            return MainWindow()


if __name__ == "__main__":
    unittest.main()
