import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.importers.postfinance_importer import parse_postfinance_pdf
from app.importers.viseca_importer import parse_viseca_pdf
from app.services.folder_sync_service import FolderSyncService


class FakeDatabase:
    def __init__(self, imported_hashes=None):
        self.imported_hashes = set(imported_hashes or [])
        self.imported_files = []
        self.inserted_sources = []

    def compute_file_hash(self, path):
        return Path(path).read_text(encoding="utf-8")

    def is_file_imported(self, filehash):
        return filehash in self.imported_hashes

    def insert_transactions(self, transactions, source_file):
        self.inserted_sources.append(source_file)
        return len(transactions)

    def add_imported_file(self, filename, filepath, filesize, filehash):
        self.imported_hashes.add(filehash)
        self.imported_files.append(filename)
        return 1


class FolderSyncServiceTests(unittest.TestCase):
    def test_importer_for_matches_supported_prefixes_case_insensitively(self):
        self.assertIs(
            FolderSyncService._importer_for(Path("Post_2026-06.pdf")),
            parse_postfinance_pdf,
        )
        self.assertIs(
            FolderSyncService._importer_for(Path("PostFinance_2026-07.pdf")),
            parse_postfinance_pdf,
        )
        self.assertIs(
            FolderSyncService._importer_for(Path("ViSeCa_2026-08.pdf")),
            parse_viseca_pdf,
        )

    def test_sync_scans_sorted_pdfs_and_counts_duplicates_and_unknowns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "2026" / "02 Februar").mkdir(parents=True)
            (root / "2026" / "01 Januar").mkdir(parents=True)
            (root / "2026" / "01 Januar" / "viseca_january.pdf").write_text("new", encoding="utf-8")
            (root / "2026" / "02 Februar" / "viseca_february.pdf").write_text("duplicate", encoding="utf-8")
            (root / "unknown.pdf").write_text("unknown", encoding="utf-8")
            (root / "notes.txt").write_text("ignored", encoding="utf-8")

            db = FakeDatabase(imported_hashes={"duplicate"})
            service = FolderSyncService(db)
            with patch("app.services.folder_sync_service.parse_viseca_pdf", return_value=[object(), object()]) as parser:
                summary = service.sync(root)

        self.assertEqual(
            summary,
            {
                "scanned_pdfs": 3,
                "new_imports": 1,
                "already_imported": 1,
                "unknown": 1,
                "transactions_imported": 2,
            },
        )
        self.assertEqual(db.inserted_sources, ["viseca_january.pdf"])
        self.assertEqual(db.imported_files, ["viseca_january.pdf"])
        parser.assert_called_once()


if __name__ == "__main__":
    unittest.main()