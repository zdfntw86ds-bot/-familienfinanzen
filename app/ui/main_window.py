from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QHeaderView,
    QStyledItemDelegate,
    QComboBox,
    QVBoxLayout,
    QWidget,
)

from app.importers import extract_text_from_pdf
from app.importers.viseca_importer import parse_viseca_pdf
from app.services.category_store import set_user_category
from app.services.categorizer import categorize


class CategoryComboDelegate(QStyledItemDelegate):
    CATEGORY_CHOICES = [
        "Lebensmittel",
        "Essen",
        "Technik",
        "Reisen",
        "Auto",
        "Gesundheit",
        "Freizeit",
        "Wohnen",
        "Software",
        "ÖV",
        "Unbekannt",
    ]

    def __init__(self, parent=None, apply_callback=None):
        super().__init__(parent)
        self.apply_callback = apply_callback

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self.CATEGORY_CHOICES)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.DisplayRole)
        if value in self.CATEGORY_CHOICES:
            editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        category = editor.currentText()
        row = index.row()
        merchant_index = index.sibling(row, 1)
        merchant = merchant_index.data(Qt.DisplayRole)
        if not merchant:
            return

        change_dialog = QMessageBox(editor.parent())
        change_dialog.setWindowTitle("Change category")
        change_dialog.setText("How should this change be applied?")
        only_this_button = change_dialog.addButton("Only this transaction", QMessageBox.AcceptRole)
        all_future_button = change_dialog.addButton("All future transactions of this merchant", QMessageBox.AcceptRole)
        cancel_button = change_dialog.addButton("Cancel", QMessageBox.RejectRole)
        change_dialog.setDefaultButton(only_this_button)
        change_dialog.exec()

        clicked_button = change_dialog.clickedButton()
        if clicked_button is cancel_button:
            return

        apply_all = clicked_button is all_future_button
        model.setData(index, category, Qt.EditRole)
        if self.apply_callback:
            self.apply_callback(row, merchant, category, apply_all)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FamilienFinanzen")
        self.resize(1200, 800)

        self._build_ui()

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.import_button = QPushButton("📄 PDF importieren", central_widget)
        self.import_button.setFixedHeight(64)
        self.import_button.clicked.connect(self._import_pdf)
        layout.addWidget(self.import_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.table = QTableWidget(0, 4, central_widget)
        self.table.setHorizontalHeaderLabels(["Date", "Merchant", "Category", "Amount (CHF)"])
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setItemDelegateForColumn(2, CategoryComboDelegate(self.table, apply_callback=self._apply_category_change))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self.setCentralWidget(central_widget)

    def _import_pdf(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "PDF auswählen",
            str(Path.home()),
            "PDF-Dateien (*.pdf)",
        )
        if not file_path:
            return

        # PDF selected
        try:
            extracted_text = extract_text_from_pdf(file_path)
        except Exception as exc:  # pragma: no cover - UI feedback path
            QMessageBox.critical(self, "Fehler", f"Die PDF-Datei konnte nicht gelesen werden.\n\n{exc}")
            return

        if not extracted_text.strip():
            QMessageBox.information(self, "Keine Textdaten", "Es konnten keine Textinhalte aus der PDF-Datei gelesen werden.")
            self.table.setRowCount(0)
            return

        # Determine importer by filename stem (only support viseca prefix for now)
        try:
            stem = Path(file_path).stem.lower()
            if stem.startswith("viseca"):
                txs = parse_viseca_pdf(file_path)
                # populate table
                # disable sorting while populating to avoid row reordering
                sorting_was_enabled = self.table.isSortingEnabled()
                self.table.setSortingEnabled(False)
                self.table.setRowCount(len(txs))
                for row, tx in enumerate(txs):
                    date_item = QTableWidgetItem(tx.date.strftime("%d.%m.%Y"))
                    merchant_item = QTableWidgetItem(tx.merchant_original)
                    category_item = QTableWidgetItem(categorize(tx.merchant_original))
                    amount_item = QTableWidgetItem(f"{tx.amount:.2f}")
                    # Right-align amount
                    amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    date_item.setFlags(date_item.flags() & ~Qt.ItemIsEditable)
                    merchant_item.setFlags(merchant_item.flags() & ~Qt.ItemIsEditable)
                    amount_item.setFlags(amount_item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(row, 0, date_item)
                    self.table.setItem(row, 1, merchant_item)
                    self.table.setItem(row, 2, category_item)
                    self.table.setItem(row, 3, amount_item)
                # Resize date and amount columns to contents; merchant/category columns stretch
                header = self.table.horizontalHeader()
                header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
                header.setSectionResizeMode(1, QHeaderView.Stretch)
                header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
                header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
                # restore sorting state
                self.table.setSortingEnabled(sorting_was_enabled)
                print(f"Parsed {len(txs)} transactions")
            else:
                QMessageBox.information(self, "Unknown importer", "Unknown importer. Please rename the file or add support for this bank.")
        except Exception as exc:  # pragma: no cover - UI feedback path
            QMessageBox.warning(self, "Parser-Fehler", f"Beim Parsen der Datei trat ein Fehler auf:\n\n{exc}")

    def _apply_category_change(self, row: int, merchant: str, category: str, apply_all: bool) -> None:
        if apply_all:
            set_user_category(merchant, category)
            updated_rows = 0
            for current_row in range(self.table.rowCount()):
                merchant_item = self.table.item(current_row, 1)
                if merchant_item and merchant_item.text() == merchant:
                    category_item = self.table.item(current_row, 2)
                    if category_item:
                        category_item.setText(category)
                        updated_rows += 1
            QMessageBox.information(
                self,
                "Rule saved",
                f"Merchant: {merchant}\n\nCategory: {category}\n\n{updated_rows} existing transactions were updated.\n\nThis category will also be used for future imports.",
            )
        else:
            category_item = self.table.item(row, 2)
            if category_item:
                category_item.setText(category)
