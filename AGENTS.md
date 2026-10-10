# Agent Instructions

## Project Overview

FamilienFinanzen is a local-first desktop application for importing and reviewing household financial transactions. The current application supports PDF imports from PostFinance and Viseca, SQLite persistence and import history, folder synchronization, category rules, and a transaction table with SQLite-backed sorting and live search.

This file is the primary instruction source for AI coding agents working in this repository. Read it before making changes; consult [ARCHITECTURE.md](ARCHITECTURE.md) for module design, [CONTRIBUTING.md](CONTRIBUTING.md) for workflow, [ROADMAP.md](ROADMAP.md) for planned work, and [CHANGELOG.md](CHANGELOG.md) for recorded changes.

## Technology Stack

- Python 3.13 or newer, below Python 4.
- PySide6 for the desktop interface.
- SQLite through Python's standard-library `sqlite3` module.
- `pdfplumber` for PDF text extraction.
- `unittest` for automated tests.
- JSON files for application settings and merchant/category rules.

## Folder Structure

```text
app/
  application.py          Application entry point
  database/               Reserved for database-specific modules
  importers/              PDF extraction and bank-specific parsing
  models/                 Domain data structures
  reports/                Reserved for reports
  services/               Persistence, categorization, and sync orchestration
  settings/               Settings persistence
  ui/                     PySide6 windows, widgets, and delegates
  utils/                  Shared utilities
config/                   User/application settings
data/                     Local database and category JSON data
docs/                     Supporting project documentation
resources/                Application assets
tests/                    Automated tests
tools/                    Developer utilities
```

Some packages are currently placeholders. Do not describe them as implemented features until code exists.

## Architecture

The application uses a layered design: UI code coordinates user interactions, services implement application operations, models represent domain data, and importer adapters convert supported bank documents into transactions. SQLite is accessed through `DatabaseService`; settings and category rules currently use JSON stores. The detailed module responsibilities and data flow are in [ARCHITECTURE.md](ARCHITECTURE.md).

Keep parsing, persistence, business rules, and widget behavior in their owning layers. Avoid adding SQL or importer parsing logic to the UI.

## Design Principles

- Keep the application local-first and make data ownership explicit.
- Prefer small changes within the existing module boundaries.
- Keep data transformations deterministic and testable without opening the GUI where possible.
- Preserve user data and existing behavior; do not silently discard or rewrite stored records.
- Validate any SQL identifiers against fixed allowlists. Bind user-provided values as parameters.
- Distinguish implemented behavior from roadmap proposals in code and documentation.

## Coding Style

- Follow PEP 8 and the patterns already used in the nearby module.
- Use descriptive names, focused functions, and type annotations on public interfaces where practical.
- Avoid unnecessary dependencies, abstractions, broad refactors, and unrelated cleanup.
- Keep comments short and explain non-obvious decisions rather than restating code.
- Do not add secrets, personal financial data, or generated database contents to source control.

## Database Rules

- `DatabaseService` owns SQLite connection setup, table initialization, and transaction/import-history queries.
- The current tables are `transactions` and `imported_files`; the current transaction columns do not persist payment method or transaction type.
- Do not change the schema casually. Schema changes require an explicit feature decision, a migration/backward-compatibility plan, and tests using temporary databases. Do not edit `data/finance.db` to implement a feature.
- Use parameterized SQL for values and allowlists for dynamic columns or ordering. Never interpolate raw user input into SQL.
- Preserve deterministic ordering where equal sort values occur.
- Search currently applies SQLite `LIKE` filtering to stored merchant and category fields; do not imply it searches unstored values.

## Importer Rules

- Importers convert supported source documents into `Transaction` model instances. Keep file selection, synchronization, duplicate detection, and database writes outside parser logic.
- Do not change importer or parser behavior as a side effect of unrelated UI or database work.
- Folder synchronization identifies supported formats from filename prefixes and deduplicates by file content hash. Preserve that behavior and cover changes with service tests.
- When adding an importer, isolate format-specific parsing, test representative input and edge cases, and register it through the existing routing boundary.

## GUI Rules

- Keep widgets and interaction wiring in `app/ui/`; delegate database operations and application workflows to services.
- Do not sort or filter a fully loaded Qt table when the requirement calls for database ordering or filtering. Use SQLite queries and populate the widget with their results.
- Preserve active search and sort state across reloads, imports, and synchronization.
- Keep UI behavior testable through focused handlers and offscreen Qt tests where practical.

## PostFinance Parser Rules

- The PostFinance importer lives in `app/importers/postfinance_importer.py`; its parsing helpers and mappings are format-specific.
- Preserve signed amounts, date interpretation, multiline booking handling, counterparty extraction, and exclusions for statement/balance lines.
- Keep changes grounded in sample statements and regression tests. Do not broaden parsing heuristics without tests for both the new case and existing cases.
- Importer-derived `payment_method` and `transaction_type` are model values today, not persisted transaction columns. Persisting them requires a separately approved schema migration.

## Testing Strategy

- Add or update focused `unittest` tests for every behavior change.
- Prefer temporary directories and temporary SQLite databases; avoid tests that depend on the user's real finance database or configuration.
- Test parser transformations independently of the GUI, service behavior independently of Qt, and user-visible wiring with focused offscreen GUI tests.
- Run the focused module first, then the complete suite with:

  ```bash
  python -m unittest discover -v
  ```

- Report commands run and their outcomes. Do not claim coverage for untested behavior.

## Git Workflow

- Work on a short-lived feature or fix branch; do not commit directly to the default branch unless the project owner requests it.
- Keep each change focused. Use imperative commit subjects with an optional area prefix (for example, `feat(search): add category filtering`).
- Review `git status` and the diff before finishing. Never discard or overwrite unrelated user changes.
- Do not commit unless explicitly asked.

## Definition of Done

- The requested behavior is implemented in the owning layer and respects stated scope restrictions.
- Relevant tests pass; new behavior has focused regression coverage.
- Documentation is updated when behavior, setup, architecture, or project direction changes.
- No unrelated changes, schema edits, or generated data modifications are included.
- Final reporting states changed files, tests, validation results, and any limitations requested by the user.

## Completed Milestones

- Application foundation with a PySide6 desktop entry point and layered package layout.
- SQLite transaction storage and imported-file history with hash-based duplicate detection.
- Viseca and PostFinance PDF import paths and recursive folder synchronization.
- Merchant categorization rules and custom category management backed by JSON stores.
- Transaction table sorting in SQLite, defaulting to date descending.
- Live SQLite search across the currently stored merchant and category fields, preserving sort state.

## Current Priorities

- Maintain correctness and test coverage for the current import, synchronization, sorting, and search workflows.
- Develop transaction management and persistence deliberately, especially where visible category edits and stored transaction values need a clear persistence contract.
- Treat payment-method and transaction-type persistence/search as future work requiring an explicit schema migration.
- Build budgeting, reporting, and dashboard capabilities only as they are implemented and verified.

See [ROADMAP.md](ROADMAP.md) for planned versions. Roadmap items are not promises of completed functionality.

## Things to Avoid

- Do not modify the importer, parser, schema, tests, or database when a task prohibits it.
- Do not search fields that are not persisted by pretending they can be queried accurately.
- Do not put SQL, PDF parsing, file-system synchronization, or category persistence logic in UI handlers.
- Do not silently alter amount signs, date semantics, import identity, or stored user data.
- Do not add speculative features, duplicate documentation, large unrelated refactors, or dependencies without need.
- Do not weaken tests to make a failing implementation pass.