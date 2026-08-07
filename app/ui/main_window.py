from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
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

        self.text_editor = QTextEdit(central_widget)
        self.text_editor.setReadOnly(True)
        self.text_editor.setPlaceholderText("Extrahierter PDF-Text erscheint hier.")
        layout.addWidget(self.text_editor)

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

        print(f"DEBUG: PDF selected: {file_path}")

        try:
            extracted_text = extract_text_from_pdf(file_path)
            print(f"DEBUG: Text extracted ({len(extracted_text or '')} chars)")
        except Exception as exc:  # pragma: no cover - UI feedback path
            QMessageBox.critical(self, "Fehler", f"Die PDF-Datei konnte nicht gelesen werden.\n\n{exc}")
            return

        if not extracted_text.strip():
            print("DEBUG: Extracted text is empty after stripping")
            QMessageBox.information(self, "Keine Textdaten", "Es konnten keine Textinhalte aus der PDF-Datei gelesen werden.")
            self.text_editor.clear()
            return

        self.text_editor.setPlainText(extracted_text)
        print("DEBUG: Displayed extracted text in QTextEdit")
        # Determine importer by filename stem (only support viseca prefix for now)
        try:
            # Print first 1000 chars for debugging
            preview = extracted_text[:1000]
            print("DEBUG: First 1000 chars of extracted text:\n" + preview)

            stem = Path(file_path).stem.lower()
            print(f"DEBUG: PDF filename stem='{stem}'")
            if stem.startswith("viseca"):
                print("DEBUG: Using Viseca importer based on filename")
                print("DEBUG: Calling parse_viseca_pdf()")
                txs = parse_viseca_pdf(file_path)
                print(f"DEBUG: Parser returned {len(txs)} transactions")
                print(f"Parsed {len(txs)} transactions")
            else:
                QMessageBox.information(self, "Unknown importer", "Unknown importer. Please rename the file or add support for this bank.")
        except Exception as exc:  # pragma: no cover - UI feedback path
            print(f"DEBUG: Parser raised exception: {exc}")
            QMessageBox.warning(self, "Parser-Fehler", f"Beim Parsen der Datei trat ein Fehler auf:\n\n{exc}")
