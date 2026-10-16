from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.services.database_service import DatabaseService


class UnknownTransactionReviewDialog(QDialog):
    def __init__(
        self,
        database: DatabaseService,
        category_creator: Callable[[], str | None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.category_creator = category_creator
        self.saved = False
        self._records = database.load_unknown_transactions()
        self._categories = {
            row["id"]: None for row in self._records
        }
        self._remember = {row["id"]: False for row in self._records}
        self._sort_column = "date"
        self._sort_direction = "DESC"
        self._sort_fields = {0: "date", 1: "merchant", 2: "amount"}

        self.setWindowTitle("Unbekannte Transaktionen kategorisieren")
        self.resize(980, 620)
        layout = QVBoxLayout(self)

        count_layout = QHBoxLayout()
        self.total_label = QLabel(self)
        self.uncategorized_label = QLabel(self)
        count_layout.addWidget(self.total_label)
        count_layout.addStretch(1)
        count_layout.addWidget(self.uncategorized_label)
        layout.addLayout(count_layout)

        batch_layout = QHBoxLayout()
        self.batch_category = QComboBox(self)
        self._fill_category_combo(self.batch_category, None)
        self.apply_batch_button = QPushButton("Kategorie auf Auswahl anwenden", self)
        self.apply_batch_button.clicked.connect(self._apply_to_selection)
        self.new_category_button = QPushButton("Kategorie erstellen", self)
        self.new_category_button.clicked.connect(self._create_category)
        batch_layout.addWidget(self.batch_category)
        batch_layout.addWidget(self.apply_batch_button)
        batch_layout.addWidget(self.new_category_button)
        batch_layout.addStretch(1)
        layout.addLayout(batch_layout)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(
            ["Datum", "Händler", "Betrag (CHF)", "Kategorie", "Regel merken"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_column)
        self.table.itemChanged.connect(self._remember_changed)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.save_button = QPushButton("Speichern", self)
        self.later_button = QPushButton("Später bearbeiten", self)
        self.cancel_button = QPushButton("Abbrechen", self)
        self.save_button.clicked.connect(self._save)
        self.later_button.clicked.connect(lambda: self.done(2))
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.later_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self._render_rows()

    def _fill_category_combo(self, combo: QComboBox, selected: str | None) -> None:
        combo.clear()
        combo.addItem("Unbekannt", None)
        for category in self.database.load_categories():
            if category.casefold() != "unbekannt":
                combo.addItem(category, category)
        index = combo.findData(selected)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _render_rows(self, selected_ids: set[int] | None = None) -> None:
        selected_ids = selected_ids or set()
        self.table.setRowCount(len(self._records))
        for row_index, record in enumerate(self._records):
            date_value = record.get("date") or ""
            try:
                date_display = datetime.fromisoformat(date_value).strftime("%d.%m.%Y")
            except (TypeError, ValueError):
                date_display = date_value
            values = [
                date_display,
                record.get("merchant") or "",
                f"{record.get('amount') or 0:.2f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if column == 0:
                    item.setData(Qt.UserRole, record["id"])
                if column == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_index, column, item)

            category_combo = QComboBox(self.table)
            self._fill_category_combo(category_combo, self._categories[record["id"]])
            category_combo.currentIndexChanged.connect(
                lambda _index, transaction_id=record["id"], widget=category_combo:
                self._category_changed(transaction_id, widget)
            )
            self.table.setCellWidget(row_index, 3, category_combo)

            remember = QTableWidgetItem()
            remember.setFlags(
                (remember.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                & ~Qt.ItemIsEditable
            )
            remember.setCheckState(
                Qt.Checked if self._remember[record["id"]] else Qt.Unchecked
            )
            self.table.setItem(row_index, 4, remember)
            remember.setData(Qt.UserRole, record["id"])
            if record["id"] in selected_ids:
                self.table.selectRow(row_index)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(1, max(260, self.table.columnWidth(1)))
        self._update_counts()

    def _category_changed(self, transaction_id: int, combo: QComboBox) -> None:
        self._categories[transaction_id] = combo.currentData()
        self._update_counts()

    def _remember_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 4:
            self._remember[item.data(Qt.UserRole)] = item.checkState() == Qt.Checked

    def _update_counts(self) -> None:
        self.total_label.setText(f"Zu prüfen: {len(self._records)}")
        remaining = sum(category is None for category in self._categories.values())
        self.uncategorized_label.setText(f"Noch nicht kategorisiert: {remaining}")

    def _apply_to_selection(self) -> None:
        selected_rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        category = self.batch_category.currentData()
        for row_index in selected_rows:
            transaction_id = self.table.item(row_index, 0).data(Qt.UserRole)
            self._categories[transaction_id] = category
        selected_ids = {
            self.table.item(row_index, 0).data(Qt.UserRole)
            for row_index in selected_rows
        }
        self._render_rows(selected_ids)

    def _create_category(self) -> None:
        category = self.category_creator()
        if not category:
            return
        canonical = self.database.add_category(category)
        self.batch_category.clear()
        self._fill_category_combo(self.batch_category, canonical)
        self._render_rows(self._selected_transaction_ids())

    def _selected_transaction_ids(self) -> set[int]:
        return {
            self.table.item(index.row(), 0).data(Qt.UserRole)
            for index in self.table.selectionModel().selectedRows()
        }

    def _sort_by_column(self, column: int) -> None:
        sort_column = self._sort_fields.get(column)
        if sort_column is None:
            return
        selected_ids = self._selected_transaction_ids()
        if self._sort_column == sort_column:
            self._sort_direction = "ASC" if self._sort_direction == "DESC" else "DESC"
        else:
            self._sort_column = sort_column
            self._sort_direction = "ASC"
        reverse = self._sort_direction == "DESC"
        self._records.sort(
            key=lambda record: (
                record.get(sort_column) or ""
                if sort_column != "amount"
                else record.get(sort_column) or 0
            ),
            reverse=reverse,
        )
        self._render_rows(selected_ids)

    def _save(self) -> None:
        rule_categories: dict[str, tuple[str, dict[str, str]]] = {}
        for record in self._records:
            transaction_id = record["id"]
            category = self._categories[transaction_id]
            if not self._remember[transaction_id] or not category:
                continue
            merchant = (record.get("merchant") or "").strip()
            if merchant:
                key = merchant.casefold()
                categories = rule_categories.setdefault(key, (merchant, {}))[1]
                categories[category.casefold()] = category

        conflicts = [
            merchant
            for merchant, categories in rule_categories.values()
            if len(categories) > 1
        ]
        if conflicts:
            QMessageBox.warning(
                self,
                "Widersprüchliche Regeln",
                "Für denselben Händler wurden unterschiedliche Kategorien zum Merken gewählt. "
                "Bitte passen Sie die Auswahl an oder deaktivieren Sie 'Regel merken'.",
            )
            return

        merchant_rules = []
        replace_merchants = set()
        for merchant, categories in rule_categories.values():
            category = next(iter(categories.values()))
            existing = self.database.get_merchant_category_rule(merchant)
            if existing and existing.casefold() != category.casefold():
                answer = QMessageBox.question(
                    self,
                    "Regel ersetzen?",
                    f"Für '{merchant}' gilt bereits die Kategorie '{existing}'. "
                    f"Soll sie durch '{category}' ersetzt werden?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer == QMessageBox.Yes:
                    replace_merchants.add(merchant)
                else:
                    continue
            merchant_rules.append((merchant, category))

        categories_by_id = {
            record["id"]: self._categories[record["id"]]
            for record in self._records
        }
        try:
            self.database.save_reviewed_transactions(
                categories_by_id,
                merchant_rules,
                replace_merchants,
            )
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Speichern fehlgeschlagen", str(exc))
            return
        self.saved = True
        self.accept()