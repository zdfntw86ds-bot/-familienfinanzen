# Changelog

All notable project changes are recorded here. This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions. Dates and release tags are added when a release is made; no release date is inferred here. Planned work is tracked separately in [ROADMAP.md](ROADMAP.md), and current module responsibilities are described in [ARCHITECTURE.md](ARCHITECTURE.md).

## [Unreleased]

### Added

- Established a Python/PySide6 desktop application foundation and a layered package structure.
- Added SQLite persistence for transactions and a separate imported-file history with content-hash duplicate detection.
- Added recursive finance-folder synchronization for supported statement PDFs.
- Added a PostFinance PDF importer alongside the Viseca import path.
- Added SQLite-backed transaction table sorting by date, merchant, category, and amount, with date descending as the default.
- Added live, case-insensitive, partial SQLite search over persisted merchant and category values; clearing search restores the full ordered list.

### Notes

- Payment method and transaction type exist on the transaction model and may be derived by importers, but are not stored in the current SQLite schema and are not searchable. Persisting and searching them is future work requiring an explicit schema migration.
- Budgeting, report generation, and dashboard functionality are planned, not implemented.