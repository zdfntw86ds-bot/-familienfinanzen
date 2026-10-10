# Architecture

## Overview

FamilienFinanzen is a local-first Python desktop application. The UI coordinates user actions; services own application workflows and persistence access; models represent transaction data; importers adapt bank documents to the model. SQLite stores transactions and imported-file history. JSON stores current application settings and categorization data.

For contribution workflow and coding constraints, see [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md). Planned capabilities are tracked in [ROADMAP.md](ROADMAP.md), while delivered changes are summarized in [CHANGELOG.md](CHANGELOG.md).

```text
                         +-------------------------+
                         |       main.py           |
                         | application startup     |
                         +------------+------------+
                                      |
                                      v
                         +-------------------------+
                         |       app/ui/           |
                         | MainWindow, table,      |
                         | dialogs, delegates      |
                         +----+---------------+----+
                              |               |
                   actions   |               | render/query results
                              v               v
             +----------------------+   +----------------------+
             | app/services/        |   | app/models/          |
             | sync, categorization,|   | Transaction          |
             | database access      |   +----------------------+
             +----+-------------+---+
                  |             |
       parse PDF  |             | SQLite / JSON
                  v             v
       +----------------+  +---------------------------+
       | app/importers/ |  | data/finance.db           |
       | extract, parse |  | data/categories*.json     |
       +----------------+  | config/settings.json      |
                           +---------------------------+

       +----------------+       +----------------------+
       | app/reports/   |       | tests/               |
       | extension area |       | unittest coverage    |
       +----------------+       +----------------------+
```

## Application Layers

### Entry Point

`main.py` delegates to `app.application.main()`, which creates or reuses the Qt application, constructs `MainWindow`, and starts the event loop. Keeping startup separate from window implementation provides a clear executable boundary.

### User Interface: `app/ui/`

`main_window.py` constructs the main window, table, controls, dialogs, and category delegate. It translates user actions into service calls and renders returned transaction rows. SQL construction, PDF parsing, and synchronization algorithms do not belong in widgets.

The transaction table requests ordered and filtered results from `DatabaseService`. Sort and search state are held by the window and passed to the loader on refresh. Search currently covers only persisted merchant and category values.

### Domain Models: `app/models/`

`transaction.py` defines the `Transaction` data structure, including date, merchant, amount, optional category, raw description, payment method, and transaction type. The model may contain values that the current database schema does not persist; callers must not assume every model attribute survives storage.

### Services: `app/services/`

- `database_service.py` owns SQLite connection setup, table creation, transaction reads/writes, ordered/search queries, and imported-file history operations.
- `folder_sync_service.py` scans folders, identifies supported PDFs by filename prefix, skips known content hashes, routes to the relevant importer, and records successful imports.
- `categorizer.py` applies built-in merchant keyword rules and saved user rules.
- `category_store.py` reads and writes merchant rules and custom category lists in JSON files.

Services isolate application workflows and storage operations from UI event handling. This makes non-visual behavior easier to test and keeps UI logic focused on interaction.

### Importers: `app/importers/`

- `pdf_importer.py` extracts text from PDF files.
- `viseca_importer.py` parses the currently supported Viseca statement format.
- `postfinance_importer.py` parses PostFinance bookings, including multiline records and format-specific transaction details.

Importers adapt source-specific formats to `Transaction` objects. They do not decide how the UI displays data or how folder synchronization records import history.

### Persistence

`DatabaseService` initializes two SQLite tables:

- `transactions`: `id`, `date`, `merchant`, `category`, `amount`, `source_file`, and `imported_at`.
- `imported_files`: file metadata, content hash, and import timestamp. `filehash` is unique and supports duplicate detection.

The default database path is `data/finance.db`. Transaction sorting uses an allowlist of supported sort columns and validated direction values. Search binds its term as a parameter and applies case-insensitive `LIKE` matching to merchant and category; wildcard characters in the input are escaped so a typed percent or underscore is treated literally. Payment method and transaction type are not currently database columns.

`config/settings.json` stores application settings such as the selected finance folder. `data/categories.json` stores merchant/category rules, and `data/custom_categories.json` stores custom category names. These JSON files are separate from transaction persistence.

### Reporting: `app/reports/`

The package is currently an extension point; report generation is not implemented. Future reports should consume service-level queries or dedicated reporting services rather than embedding financial calculations in the UI.

## Data Flow

### PDF Import

1. The user selects a PDF or requests folder synchronization.
2. The application selects a supported importer using the filename prefix.
3. The importer extracts and parses bank-specific booking data into `Transaction` objects.
4. `DatabaseService` stores supported transaction columns and source metadata in SQLite.
5. Successful file metadata and its content hash are recorded in `imported_files`.
6. The UI reloads rows using the current SQL sort and search state.

### Folder Synchronization

`FolderSyncService` recursively scans PDF files in stable path order, hashes each file, skips hashes already present, routes supported filename prefixes, and asks services to store transactions and import history. The UI refreshes the table after synchronization.

### Search and Sorting

The table header updates the active sort key and direction. The search field reloads on each text change. Both values are passed to `DatabaseService`, which applies SQL `ORDER BY` and optional `WHERE ... LIKE` before returning rows. Clearing the field sends an empty search term and restores the full list in the active order.

## Extension Points

- Add persistent transaction attributes only with an approved SQLite migration and backward-compatibility tests; model fields alone do not imply database support.
- Add new sort/search fields by extending the database query through fixed allowlists and parameterized values.
- Add import formats as isolated adapters and register routing in the sync/import boundary.
- Add reporting in `app/reports/` and keep calculations in testable service/domain functions.
- Consider a dedicated repository abstraction if persistence grows beyond the current service, but avoid introducing it without concrete complexity it resolves.

## Design Philosophy

Keep the application local-first, explicit, and testable. Separate format adaptation, application workflows, persistence, domain data, and presentation so each can change without entangling the others. Prefer small, reversible changes; protect user financial data; and document planned functionality separately from implemented behavior.