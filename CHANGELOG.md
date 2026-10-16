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
- Added composable SQLite filters for date periods, categories, and amount ranges, with German controls and filter reset.
- Added persistent SQLite merchant-category rules, applied before existing keyword/JSON categorization on import.
- Added batch review of unknown transactions after PDF imports and folder synchronization, with individual or multi-row category assignment, persistent SQLite category definitions, optional remembered merchant rules, explicit rule-replacement confirmation, and a main-window review-later entry point.
- Updated explicit merchant-rule saves to categorize existing exact merchant matches that remain unknown, while preserving already categorized transactions and applying rule persistence plus retroactive updates atomically.

### Notes

- Payment method and transaction type exist on the transaction model and may be derived by importers, but are not stored in the current SQLite schema and are not searchable. Persisting and searching them is future work requiring an explicit schema migration.
- Budgeting, report generation, and dashboard functionality are planned, not implemented.