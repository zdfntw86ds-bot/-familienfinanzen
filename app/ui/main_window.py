from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QDate, QSignalBlocker, Qt
from PySide6.QtGui import QDoubleValidator
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
    QLineEdit,
    QFormLayout,
    QDateEdit,
)

from app.importers import extract_text_from_pdf
from app.importers.postfinance_importer import parse_postfinance_pdf
from app.importers.viseca_importer import parse_viseca_pdf
from app.services.database_service import DatabaseService
from app.services.folder_sync_service import FolderSyncService
from app.settings import load_settings, save_settings
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
from app.ui.unknown_transaction_review_dialog import UnknownTransactionReviewDialog


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
        change_dialog.setWindowTitle("Kategorie ändern")
        change_dialog.setText("Wie soll diese Änderung angewendet werden?")
        only_this_button = change_dialog.addButton("Nur diese Transaktion", QMessageBox.AcceptRole)
        all_future_button = change_dialog.addButton("Alle zukünftigen Transaktionen dieses Händlers", QMessageBox.AcceptRole)
        cancel_button = change_dialog.addButton("Abbrechen", QMessageBox.RejectRole)
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

        # initialize database service and load existing transactions
        self.db = DatabaseService()
        self.folder_sync_service = FolderSyncService(self.db)
        self.finance_folder = load_settings().get("finance_folder")
        self._update_finance_folder_label()
        print(f"[UI DEBUG] using database at: {self.db.db_path}")
        self._load_transactions_from_db()
        self._update_status_bar()

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.import_button = QPushButton("📄 PDF importieren", central_widget)
        self.import_button.setFixedHeight(64)
        self.import_button.clicked.connect(self._import_pdf)
        layout.addWidget(self.import_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.unknown_transactions_button = QPushButton("Unbekannte Transaktionen (0)", central_widget)
        self.unknown_transactions_button.setFixedHeight(48)
        self.unknown_transactions_button.clicked.connect(self._open_unknown_review)
        layout.addWidget(self.unknown_transactions_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.select_folder_button = QPushButton("📂 Select Finance Folder", central_widget)
        self.select_folder_button.setFixedHeight(48)
        self.select_folder_button.clicked.connect(self._select_finance_folder)
        layout.addWidget(self.select_folder_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.sync_button = QPushButton("🔄 Synchronize", central_widget)
        self.sync_button.setFixedHeight(48)
        self.sync_button.clicked.connect(self._synchronize_folder)
        layout.addWidget(self.sync_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.finance_folder_label = QLabel(central_widget)
        self.finance_folder_label.setWordWrap(True)
        layout.addWidget(self.finance_folder_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.manage_categories_button = QPushButton("⚙️ Kategorien verwalten", central_widget)
        self.manage_categories_button.setFixedHeight(48)
        self.manage_categories_button.clicked.connect(self._open_manage_categories_dialog)
        layout.addWidget(self.manage_categories_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.search_field = QLineEdit(central_widget)
        self.search_field.setPlaceholderText("Händler oder Kategorie suchen")
        self.search_field.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_field)

        filter_layout = QHBoxLayout()
        self.date_filter = QComboBox(central_widget)
        self.date_filter.addItems(
            [
                "Alle Daten",
                "Aktueller Monat",
                "Letzter Monat",
                "Aktuelles Jahr",
                "Benutzerdefiniert",
            ]
        )
        self.date_filter.currentIndexChanged.connect(self._on_date_filter_changed)
        filter_layout.addWidget(self.date_filter)

        self.date_from_filter = QDateEdit(QDate.currentDate(), central_widget)
        self.date_from_filter.setCalendarPopup(True)
        self.date_from_filter.setDisplayFormat("dd.MM.yyyy")
        self.date_from_filter.setToolTip("Von")
        self.date_from_filter.dateChanged.connect(self._on_filter_changed)
        self.date_from_filter.hide()
        filter_layout.addWidget(self.date_from_filter)

        self.date_to_filter = QDateEdit(QDate.currentDate(), central_widget)
        self.date_to_filter.setCalendarPopup(True)
        self.date_to_filter.setDisplayFormat("dd.MM.yyyy")
        self.date_to_filter.setToolTip("Bis")
        self.date_to_filter.dateChanged.connect(self._on_filter_changed)
        self.date_to_filter.hide()
        filter_layout.addWidget(self.date_to_filter)

        self.category_filter = QComboBox(central_widget)
        self.category_filter.addItem("Alle Kategorien", None)
        self.category_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.category_filter)

        self.min_amount_filter = QLineEdit(central_widget)
        self.min_amount_filter.setPlaceholderText("Betrag von (CHF)")
        self.min_amount_filter.setValidator(QDoubleValidator(-1e12, 1e12, 2, self.min_amount_filter))
        self.min_amount_filter.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.min_amount_filter)

        self.max_amount_filter = QLineEdit(central_widget)
        self.max_amount_filter.setPlaceholderText("Betrag bis (CHF)")
        self.max_amount_filter.setValidator(QDoubleValidator(-1e12, 1e12, 2, self.max_amount_filter))
        self.max_amount_filter.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.max_amount_filter)

        self.reset_filters_button = QPushButton("Filter zurücksetzen", central_widget)
        self.reset_filters_button.clicked.connect(self._reset_filters)
        filter_layout.addWidget(self.reset_filters_button)
        layout.addLayout(filter_layout)

        self.table = QTableWidget(0, 4, central_widget)
        self.table.setHorizontalHeaderLabels(["Date", "Merchant", "Category", "Amount (CHF)"])
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self._sort_column = "date"
        self._sort_direction = "DESC"
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.setItemDelegateForColumn(2, CategoryComboDelegate(self.table, apply_callback=self._apply_category_change, categories_loader=load_custom_categories))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self.setCentralWidget(central_widget)

    def _update_finance_folder_label(self) -> None:
        if not hasattr(self, "finance_folder_label"):
            return
        folder = self.finance_folder or "No finance folder selected."
        self.finance_folder_label.setText(str(folder))

    def _select_finance_folder(self) -> None:
        current_folder = self.finance_folder or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select Finance Folder", current_folder)
        if not folder:
            return

        self.finance_folder = folder
        settings = load_settings()
        settings["finance_folder"] = folder
        save_settings(settings)
        self._update_finance_folder_label()

    def _synchronize_folder(self) -> None:
        if not self.finance_folder:
            return

        summary = self.folder_sync_service.sync(self.finance_folder)
        self._load_transactions_from_db()
        self._update_status_bar()
        if self.db.count_unknown_transactions():
            self._open_unknown_review()
        message = (
            "Synchronization finished.\n\n"
            f"Scanned PDFs:\n{summary['scanned_pdfs']}\n\n"
            f"New imports:\n{summary['new_imports']}\n\n"
            f"Already imported:\n{summary['already_imported']}\n\n"
            f"Unknown:\n{summary['unknown']}\n\n"
            f"Transactions imported:\n{summary['transactions_imported']}"
        )
        QMessageBox.information(self, "Synchronization finished", message)

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
            file_hash = self.db.compute_file_hash(file_path)
        except Exception as exc:  # pragma: no cover - IO failures
            QMessageBox.critical(self, "Fehler", f"Die Datei konnte nicht gelesen werden.\n\n{exc}")
            return

        print(f"[UI DEBUG] computed file hash: {file_hash}")

        # Duplicate detection by file hash
        try:
            imported_count = self.db.get_imported_file_count()
            print(f"[UI DEBUG] imported_files current count: {imported_count}")
        except Exception as exc:
            print(f"[UI DEBUG] get_imported_file_count raised: {exc}")

        try:
            imported = self.db.is_file_imported(file_hash)
            print(f"[UI DEBUG] is_file_imported returned: {imported}")
            if imported:
                filename_only = Path(file_path).name
                imported_meta = None
                try:
                    imported_meta = self.db.get_imported_file(file_hash)
                except Exception:
                    imported_meta = None

                message_lines = ["This PDF has already been imported.", "", "File:", f"{filename_only}"]
                if imported_meta and imported_meta.get("imported_at"):
                    message_lines.extend(["", "Imported on:", f"{imported_meta.get('imported_at')}"])
                message_lines.extend(["", "No transactions were imported."])
                QMessageBox.information(self, "Already imported", "\n".join(message_lines))
                return
        except Exception as exc:
            print(f"[UI DEBUG] is_file_imported raised exception: {exc}")
            # if duplicate check fails, continue to attempt import
            pass

        try:
            extracted_text = extract_text_from_pdf(file_path)
        except Exception as exc:  # pragma: no cover - UI feedback path
            QMessageBox.critical(self, "Fehler", f"Die PDF-Datei konnte nicht gelesen werden.\n\n{exc}")
            return

        if not extracted_text.strip():
            QMessageBox.information(self, "Keine Textdaten", "Es konnten keine Textinhalte aus der PDF-Datei gelesen werden.")
            self.table.setRowCount(0)
            return

        # Determine importer by filename stem.
        try:
            stem = Path(file_path).stem.lower()
            if stem.startswith("viseca"):
                importer = parse_viseca_pdf
            elif stem.startswith("post"):
                importer = parse_postfinance_pdf
            else:
                QMessageBox.information(self, "Unknown importer", "Unknown importer. Please rename the file or add support for this bank.")
                return

            print("[UI DEBUG] parsing will start")
            txs = importer(file_path)
            print(f"[UI DEBUG] parsing finished, parsed {len(txs)} transactions")
            # store parsed transactions in the database
            try:
                print("[UI DEBUG] inserting transactions into DB")
                inserted = self.db.insert_transactions(txs, Path(file_path).name)
                print(f"[UI DEBUG] insert_transactions returned: {inserted}")
            except Exception as exc:  # pragma: no cover - DB failures
                QMessageBox.critical(self, "Fehler", f"Import in die Datenbank fehlgeschlagen:\n\n{exc}")
                return

            # record imported file (remember every imported PDF)
            try:
                filesize = Path(file_path).stat().st_size
            except Exception:
                filesize = 0
            try:
                print("[UI DEBUG] calling add_imported_file")
                add_id = self.db.add_imported_file(Path(file_path).name, str(Path(file_path)), filesize, file_hash)
                print(f"[UI DEBUG] add_imported_file returned: {add_id}")
            except Exception as exc:
                print(f"[UI DEBUG] add_imported_file raised exception: {exc}")
                # failure to record imported file should not block the rest
                pass

            # reload all transactions from database and populate the table
            self._load_transactions_from_db()
            self._update_status_bar()
            if self.db.count_unknown_transactions():
                self._open_unknown_review()
            print(f"Imported {inserted} transactions")
        except Exception as exc:  # pragma: no cover - UI feedback path
            QMessageBox.warning(self, "Parser-Fehler", f"Beim Parsen der Datei trat ein Fehler auf:\n\n{exc}")

    def _apply_category_change(self, row: int, merchant: str, category: str, apply_all: bool) -> None:
        if apply_all:
            self.db.save_merchant_category_rule(
                merchant,
                category,
                replace_existing=True,
            )
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

    def _open_unknown_review(self) -> None:
        if not hasattr(self, "db"):
            return
        dialog = UnknownTransactionReviewDialog(
            self.db,
            category_creator=lambda: self._create_category(self),
            parent=self,
        )
        dialog.exec()
        self._load_transactions_from_db()
        self._update_status_bar()
        if dialog.saved:
            remaining = self.db.count_unknown_transactions()
            QMessageBox.information(
                self,
                "Speichern abgeschlossen",
                f"Noch uncategorisierte Transaktionen: {remaining}",
            )

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
        added = self._create_category(parent)
        if not added:
            return

        QMessageBox.information(parent, "Kategorie hinzugefügt", f"Kategorie '{added}' wurde hinzugefügt.")
        self._populate_category_list()

    def _create_category(self, parent: QWidget) -> str | None:
        new_category, ok = QInputDialog.getText(parent, "Neue Kategorie", "Kategorie hinzufügen:")
        if not ok or not new_category.strip():
            return None
        normalized = new_category.strip()
        for category in self.db.load_categories():
            if category.casefold() == normalized.casefold():
                return category
        added = add_custom_category(normalized)
        return self.db.add_category(added) if added else None

    def _rename_category(self, parent: QWidget) -> None:
        category = self._get_selected_category()
        if not category:
            QMessageBox.information(parent, "Keine Auswahl", "Bitte wählen Sie zuerst eine Kategorie aus.")
            return

        new_name, ok = QInputDialog.getText(parent, "Kategorie umbenennen", "Neuer Kategoriename:", text=category)
        if not ok or not new_name.strip():
            return

        normalized_new = new_name.strip()
        updated_rules = rename_custom_category(category, normalized_new)

        # Determine whether the rename actually succeeded in the custom categories store.
        custom_cats = load_custom_categories()
        succeeded = any(c.lower() == normalized_new.lower() for c in custom_cats)
        if not succeeded:
            QMessageBox.warning(parent, "Umbenennen fehlgeschlagen", "Die neue Kategorie existiert bereits oder ist ungültig.")
            return
        self.db.update_merchant_category_rules(category, normalized_new)

        # Count transactions that will be updated in the current table view
        updated_transactions = 0
        for row in range(self.table.rowCount()):
            category_item = self.table.item(row, 2)
            if category_item and category_item.text() == category:
                updated_transactions += 1

        QMessageBox.information(
            parent,
            "Category renamed successfully",
            f"Category renamed successfully\n\nOld category:\n{category}\n\nNew category:\n{normalized_new}\n\nUpdated:\n\n• {updated_transactions} transactions\n• {updated_rules} merchant rules",
        )
        self._populate_category_list()
        self._refresh_transaction_categories(changed_categories=[category, normalized_new])

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
        self.db.update_merchant_category_rules(category, replacement_value)

        # Count transactions that will be updated in the current table view
        updated_transactions = 0
        for row in range(self.table.rowCount()):
            category_item = self.table.item(row, 2)
            if category_item and category_item.text() == category:
                updated_transactions += 1

        # Replacement display value
        replacement_display = replacement if replacement_value is not None else "Unbekannt"

        QMessageBox.information(
            parent,
            "Category deleted successfully",
            f"Category deleted successfully\n\nOld category:\n{category}\n\nReplacement:\n{replacement_display}\n\nUpdated:\n\n• {updated_transactions} transactions\n• {rules_updated} merchant rules",
        )
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
        self.db.update_merchant_category_rules(source, target)

        # Count transactions that will be updated in the current table view
        updated_transactions = 0
        for row in range(self.table.rowCount()):
            category_item = self.table.item(row, 2)
            if category_item and category_item.text() == source:
                updated_transactions += 1

        QMessageBox.information(
            parent,
            "Category merged successfully",
            f"Category merged successfully\n\nOld category:\n{source}\n\nNew category:\n{target}\n\nUpdated:\n\n• {updated_transactions} transactions\n• {updated_rules} merchant rules",
        )
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

    def _populate_table_from_db(self, rows: list[dict]) -> None:
        # rows: list of dicts with keys: id, date (ISO), merchant, category, amount, source_file, imported_at
        sorting_was_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            # format date from ISO to dd.mm.YYYY if possible
            date_str = row.get("date") or ""
            try:
                dt = datetime.fromisoformat(date_str)
                date_display = dt.strftime("%d.%m.%Y")
            except Exception:
                date_display = date_str

            merchant = row.get("merchant") or ""
            category = row.get("category") if row.get("category") is not None else categorize(merchant)
            amount = row.get("amount") or 0.0

            date_item = QTableWidgetItem(date_display)
            merchant_item = QTableWidgetItem(merchant)
            category_item = QTableWidgetItem(category)
            amount_item = QTableWidgetItem(f"{amount:.2f}")
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            date_item.setFlags(date_item.flags() & ~Qt.ItemIsEditable)
            merchant_item.setFlags(merchant_item.flags() & ~Qt.ItemIsEditable)
            amount_item.setFlags(amount_item.flags() & ~Qt.ItemIsEditable)

            self.table.setItem(row_index, 0, date_item)
            self.table.setItem(row_index, 1, merchant_item)
            self.table.setItem(row_index, 2, category_item)
            self.table.setItem(row_index, 3, amount_item)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSortingEnabled(sorting_was_enabled)

    def _load_transactions_from_db(self) -> None:
        self._refresh_category_filter_options()
        filters = self._transaction_filter_values()
        if filters:
            rows = self.db.load_all_transactions(
                self._sort_column,
                self._sort_direction,
                self.search_field.text(),
                **filters,
            )
        else:
            rows = self.db.load_all_transactions(
                self._sort_column,
                self._sort_direction,
                self.search_field.text(),
            )
        self._populate_table_from_db(rows)
        if hasattr(self, "unknown_transactions_button"):
            unknown_count = self.db.count_unknown_transactions()
            self.unknown_transactions_button.setText(
                f"Unbekannte Transaktionen ({unknown_count})"
            )

    def _transaction_filter_values(self) -> dict[str, str | float]:
        filters: dict[str, str | float] = {}
        selected_category = self.category_filter.currentData()
        if selected_category:
            filters["category"] = selected_category

        date_mode = self.date_filter.currentIndex()
        today = QDate.currentDate()
        if date_mode == 1:
            start = QDate(today.year(), today.month(), 1)
            end = start.addMonths(1).addDays(-1)
            filters["date_from"] = start.toString("yyyy-MM-dd")
            filters["date_to"] = end.toString("yyyy-MM-dd")
        elif date_mode == 2:
            current_month = QDate(today.year(), today.month(), 1)
            end = current_month.addDays(-1)
            start = QDate(end.year(), end.month(), 1)
            filters["date_from"] = start.toString("yyyy-MM-dd")
            filters["date_to"] = end.toString("yyyy-MM-dd")
        elif date_mode == 3:
            filters["date_from"] = QDate(today.year(), 1, 1).toString("yyyy-MM-dd")
            filters["date_to"] = QDate(today.year(), 12, 31).toString("yyyy-MM-dd")
        elif date_mode == 4:
            filters["date_from"] = self.date_from_filter.date().toString("yyyy-MM-dd")
            filters["date_to"] = self.date_to_filter.date().toString("yyyy-MM-dd")

        min_amount = self._amount_filter_value(self.min_amount_filter.text())
        max_amount = self._amount_filter_value(self.max_amount_filter.text())
        if min_amount is not None:
            filters["min_amount"] = min_amount
        if max_amount is not None:
            filters["max_amount"] = max_amount
        return filters

    @staticmethod
    def _amount_filter_value(value: str) -> float | None:
        normalized = value.strip().replace(",", ".")
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None

    def _refresh_category_filter_options(self) -> None:
        selected = self.category_filter.currentData()
        categories = self.db.load_categories()
        blocker = QSignalBlocker(self.category_filter)
        self.category_filter.clear()
        self.category_filter.addItem("Alle Kategorien", None)
        seen_categories = set()
        for category in categories:
            normalized = category.casefold()
            if normalized == "unbekannt" or normalized in seen_categories:
                continue
            seen_categories.add(normalized)
            self.category_filter.addItem(category, category)
        self.category_filter.addItem("Unbekannt", "Unbekannt")
        if selected:
            index = self.category_filter.findData(selected)
            if index >= 0:
                self.category_filter.setCurrentIndex(index)
        del blocker

    def _on_date_filter_changed(self, index: int) -> None:
        custom_range = index == 4
        self.date_from_filter.setVisible(custom_range)
        self.date_to_filter.setVisible(custom_range)
        self._load_transactions_from_db()

    def _on_filter_changed(self, *_args) -> None:
        self._load_transactions_from_db()

    def _reset_filters(self) -> None:
        blockers = [
            QSignalBlocker(widget)
            for widget in (
                self.date_filter,
                self.date_from_filter,
                self.date_to_filter,
                self.category_filter,
                self.min_amount_filter,
                self.max_amount_filter,
                self.search_field,
            )
        ]
        self.date_filter.setCurrentIndex(0)
        self.date_from_filter.setDate(QDate.currentDate())
        self.date_to_filter.setDate(QDate.currentDate())
        self.category_filter.setCurrentIndex(0)
        self.min_amount_filter.clear()
        self.max_amount_filter.clear()
        self.search_field.clear()
        self.date_from_filter.hide()
        self.date_to_filter.hide()
        del blockers
        self._load_transactions_from_db()

    def _on_search_changed(self, search_term: str) -> None:
        self._load_transactions_from_db()

    def _on_header_clicked(self, column: int) -> None:
        sort_columns = {0: "date", 1: "merchant", 2: "category", 3: "amount"}
        selected_column = sort_columns.get(column)
        if selected_column is None:
            return

        if selected_column == self._sort_column:
            self._sort_direction = "ASC" if self._sort_direction == "DESC" else "DESC"
        else:
            self._sort_column = selected_column
            self._sort_direction = "ASC"

        self._load_transactions_from_db()

    def _update_status_bar(self) -> None:
        count = self.db.count_transactions()
        imported_count = 0
        try:
            imported_count = self.db.get_imported_file_count()
        except Exception:
            imported_count = 0

        self.statusBar().showMessage(f"Database: {count} transactions | Imported PDFs: {imported_count}")
