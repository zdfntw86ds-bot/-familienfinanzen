from pathlib import Path

from app.importers.postfinance_importer import parse_postfinance_pdf
from app.importers.viseca_importer import parse_viseca_pdf
from app.services.database_service import DatabaseService


class FolderSyncService:
    def __init__(self, db: DatabaseService) -> None:
        self.db = db

    def sync(self, folder: str | Path) -> dict[str, int]:
        folder_path = Path(folder)
        pdf_paths = sorted(
            (path for path in folder_path.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"),
            key=lambda path: str(path).lower(),
        )
        summary = {
            "scanned_pdfs": len(pdf_paths),
            "new_imports": 0,
            "already_imported": 0,
            "unknown": 0,
            "transactions_imported": 0,
        }

        for pdf_path in pdf_paths:
            file_hash = self.db.compute_file_hash(pdf_path)
            if self.db.is_file_imported(file_hash):
                summary["already_imported"] += 1
                continue

            importer = self._importer_for(pdf_path)
            if importer is None:
                summary["unknown"] += 1
                print(f"Unknown importer: {pdf_path.name}")
                continue

            try:
                transactions = importer(pdf_path)
                inserted = self.db.insert_transactions(transactions, pdf_path.name)
                filesize = pdf_path.stat().st_size
                self.db.add_imported_file(pdf_path.name, str(pdf_path), filesize, file_hash)
            except Exception as exc:
                print(f"Import failed: {pdf_path.name}: {exc}")
                continue

            summary["new_imports"] += 1
            summary["transactions_imported"] += inserted

        return summary

    @staticmethod
    def _importer_for(path: Path):
        stem = path.stem.lower()
        if stem.startswith("viseca"):
            return parse_viseca_pdf
        if stem.startswith("post"):
            return parse_postfinance_pdf
        return None