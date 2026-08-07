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
    QInputDialog,
    QStyledItemDelegate,
    QComboBox,
    QVBoxLayout,
    QWidget,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QFormLayout,
)

from app.importers import extract_text_from_pdf
from app.importers.viseca_importer import parse_viseca_pdf
from app.services.category_store import (
    add_custom_category,
    delete_custom_category,
    get_user_category,
    load_categories,
    load_custom_categories,
    merge_category,
    rename_custom_category,
    set_user_category,
)
from app.services.categorizer import categorize


class CategoryComboDelegate(QStyledItemDelegate):
    BUILT_IN_CATEGORIES = [
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
    NEW_CATEGORY_LABEL = "+ New category..."

    def __init__(self, parent=None, apply_callback=None, categories_loader=None):
        super().__init__(parent)
        self.apply_callback = apply_callback
        self.categories_loader = categories_loader

    def _category_list(self) -> list[str]:
        categories = list(self.BUILT_IN_CATEGORIES)
        if self.categories_loader:
            custom = self.categories_loader()
            categories.extend(custom)
        categories = sorted(set(categories), key=lambda item: item.lower())
        categories.append(self.NEW_CATEGORY_LABEL)
        return categories

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self._category_list())
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.DisplayRole)
        if value in self._category_list():
            editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        category = editor.currentText()
        row = index.row()
        previous_category = index.model().data(index, Qt.DisplayRole)
        if category == self.NEW_CATEGORY_LABEL:
            new_category, ok = QInputDialog.getText(editor.parent(), "New category", "Category name:")
            if not ok or not new_category.strip():
                model.setData(index, previous_category, Qt.EditRole)
                return

            new_category = new_category.strip()
            for existing in self._category_list():
                if existing.lower() == new_category.lower() and existing != self.NEW_CATEGORY_LABEL:
                    category = existing
                    break
            else:
                category = add_custom_category(new_category)
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
            model.setData(index, previous_category, Qt.EditRole)
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

        self.manage_categories_button = QPushButton("⚙️ Kategorien verwalten", central_widget)
        self.manage_categories_button.setFixedHeight(48)
        self.manage_categories_button.clicked.connect(self._open_manage_categories_dialog)
        layout.addWidget(self.manage_categories_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.table = QTableWidget(0, 4, central_widget)
        self.table.setHorizontalHeaderLabels(["Date", "Merchant", "Category", "Amount (CHF)"])
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setItemDelegateForColumn(2, CategoryComboDelegate(self.table, apply_callback=self._apply_category_change, categories_loader=load_custom_categories))
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

    def _open_manage_categories_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Kategorien verwalten")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info_label = QLabel("Benutzerdefinierte Kategorien bearbeiten und vorhandene Regeln verwalten.")
        layout.addWidget(info_label)

        self.category_list_widget = QListWidget(dialog)
        self._populate_category_list()
        layout.addWidget(self.category_list_widget)

        button_layout = QHBoxLayout()
        add_button = QPushButton("Neu", dialog)
        rename_button = QPushButton("Umbenennen", dialog)
        delete_button = QPushButton("Löschen", dialog)
        merge_button = QPushButton("Zusammenführen", dialog)
        close_button = QPushButton("Schließen", dialog)

        add_button.clicked.connect(lambda: self._add_category(dialog))
        rename_button.clicked.connect(lambda: self._rename_category(dialog))
        delete_button.clicked.connect(lambda: self._delete_category(dialog))
        merge_button.clicked.connect(lambda: self._merge_category(dialog))
        close_button.clicked.connect(dialog.accept)

        button_layout.addWidget(add_button)
        button_layout.addWidget(rename_button)
        button_layout.addWidget(delete_button)
        button_layout.addWidget(merge_button)
        button_layout.addStretch(1)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

        dialog.exec()

    def _populate_category_list(self) -> None:
        if not hasattr(self, "category_list_widget"):
            return

        self.category_list_widget.clear()
        for category in load_custom_categories():
            item = QListWidgetItem(category)
            self.category_list_widget.addItem(item)

    def _get_selected_category(self) -> str | None:
        selected_items = self.category_list_widget.selectedItems()
        if not selected_items:
            return None
        return selected_items[0].text()

    def _add_category(self, parent: QWidget) -> None:
        new_category, ok = QInputDialog.getText(parent, "Neue Kategorie", "Kategorie hinzufügen:")
        if not ok or not new_category.strip():
            return

        added = add_custom_category(new_category.strip())
        if not added:
            QMessageBox.warning(parent, "Ungültig", "Der Kategoriename darf nicht leer sein.")
            return

        QMessageBox.information(parent, "Kategorie hinzugefügt", f"Kategorie '{added}' wurde hinzugefügt.")
        self._populate_category_list()

    def _rename_category(self, parent: QWidget) -> None:
        category = self._get_selected_category()
        if not category:
            QMessageBox.information(parent, "Keine Auswahl", "Bitte wählen Sie zuerst eine Kategorie aus.")
            return

        new_name, ok = QInputDialog.getText(parent, "Kategorie umbenennen", "Neuer Kategoriename:", text=category)
        if not ok or not new_name.strip():
            return

        updated_rules = rename_custom_category(category, new_name.strip())
        if updated_rules == 0 and new_name.strip().lower() != category.lower():
            QMessageBox.warning(parent, "Umbenennen fehlgeschlagen", "Die neue Kategorie existiert bereits oder ist ungültig.")
            return

        QMessageBox.information(parent, "Kategorie umbenannt", f"'{category}' wurde in '{new_name.strip()}' umbenannt.\n{updated_rules} Regel(n) aktualisiert.")
        self._populate_category_list()
        self._refresh_transaction_categories(changed_categories=[category, new_name.strip()])

    def _delete_category(self, parent: QWidget) -> None:
        category = self._get_selected_category()
        if not category:
            QMessageBox.information(parent, "Keine Auswahl", "Bitte wählen Sie zuerst eine Kategorie aus.")
            return

        replacement, ok = self._select_replacement_category(parent, f"Kategorie '{category}' löschen", "Wählen Sie eine Ersatzkategorie für vorhandene Regeln:")
        if not ok:
            return

        if replacement == "Unbekannt":
            replacement_value = None
        else:
            replacement_value = replacement

        rules_updated = delete_custom_category(category, replacement_value)
        QMessageBox.information(parent, "Kategorie gelöscht", f"'{category}' wurde gelöscht.\n{rules_updated} Regel(n) wurden aktualisiert.")
        self._populate_category_list()
        self._refresh_transaction_categories(changed_categories=[category])

    def _merge_category(self, parent: QWidget) -> None:
        source = self._get_selected_category()
        if not source:
            QMessageBox.information(parent, "Keine Auswahl", "Bitte wählen Sie zuerst eine Kategorie aus.")
            return

        target, ok = self._select_replacement_category(parent, f"Kategorie '{source}' zusammenführen", "Wählen Sie die Zielkategorie:", allow_unknown=False)
        if not ok or target == source:
            return

        preview_count = self._count_rules_for_category(source)
        if preview_count == 0:
            QMessageBox.information(parent, "Keine Regel getroffen", f"Es gibt keine Regeln mit der Kategorie '{source}'.")
            return

        preview_dialog = QMessageBox(parent)
        preview_dialog.setWindowTitle("Vorschau Zusammenführen")
        preview_dialog.setText(
            f"Sie führen '{source}' in '{target}' zusammen.\n\n{preview_count} Regel(n) werden auf '{target}' aktualisiert."
        )
        preview_dialog.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        preview_dialog.setDefaultButton(QMessageBox.Ok)
        if preview_dialog.exec() != QMessageBox.Ok:
            return

        updated_rules = merge_category(source, target)
        QMessageBox.information(parent, "Zusammengeführt", f"'{source}' wurde in '{target}' zusammengeführt.\n{updated_rules} Regel(n) aktualisiert.")
        self._populate_category_list()
        self._refresh_transaction_categories(changed_categories=[source, target])

    def _select_replacement_category(self, parent: QWidget, title: str, label: str, allow_unknown: bool = True) -> tuple[str, bool]:
        dialog = QDialog(parent)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form_layout = QFormLayout()
        combo = QComboBox(dialog)
        categories = ["Unbekannt"] if allow_unknown else []
        categories.extend(sorted(set(CategoryComboDelegate.BUILT_IN_CATEGORIES + load_custom_categories()), key=lambda item: item.lower()))
        combo.addItems(categories)
        form_layout.addRow(QLabel(label, dialog), combo)
        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        result = dialog.exec()
        return combo.currentText(), result == QDialog.Accepted

    def _count_rules_for_category(self, category: str) -> int:
        categories = load_categories()
        return sum(1 for value in categories.values() if value == category)

    def _refresh_transaction_categories(self, changed_categories: list[str] | None = None) -> None:
        changed_set = set(changed_categories or [])
        for row in range(self.table.rowCount()):
            merchant_item = self.table.item(row, 1)
            category_item = self.table.item(row, 2)
            if not merchant_item or not category_item:
                continue

            merchant = merchant_item.text()
            current_category = category_item.text()
            stored_category = get_user_category(merchant)
            if stored_category is not None and current_category != stored_category:
                category_item.setText(stored_category)
                continue

            if changed_set and current_category in changed_set:
                category_item.setText(categorize(merchant))

        self.table.viewport().update()
