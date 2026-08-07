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
    QVBoxLayout,
    QWidget,
)

from app.importers import extract_text_from_pdf
from app.importers.viseca_importer import parse_viseca_pdf


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

        self.table = QTableWidget(0, 3, central_widget)
        self.table.setHorizontalHeaderLabels(["Date", "Merchant", "Amount (CHF)"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
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
                self.table.setRowCount(len(txs))
                for row, tx in enumerate(txs):
                    date_item = QTableWidgetItem(tx.date.strftime("%d.%m.%Y"))
                    merchant_item = QTableWidgetItem(tx.merchant_original)
                    amount_item = QTableWidgetItem(f"{tx.amount:.2f}")
                    self.table.setItem(row, 0, date_item)
                    self.table.setItem(row, 1, merchant_item)
                    self.table.setItem(row, 2, amount_item)
                print(f"Parsed {len(txs)} transactions")
            else:
                QMessageBox.information(self, "Unknown importer", "Unknown importer. Please rename the file or add support for this bank.")
        except Exception as exc:  # pragma: no cover - UI feedback path
            QMessageBox.warning(self, "Parser-Fehler", f"Beim Parsen der Datei trat ein Fehler auf:\n\n{exc}")
