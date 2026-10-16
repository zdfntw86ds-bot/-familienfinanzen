# Roadmap

This roadmap describes the intended direction of FamilienFinanzen. Checkboxes distinguish completed work from planned work; unchecked items are not implemented commitments. Keep entries concise and update them when scope changes or work is completed. For implementation boundaries, see [ARCHITECTURE.md](ARCHITECTURE.md); for completed changes, see [CHANGELOG.md](CHANGELOG.md).

## Version 0.1: Core Infrastructure

- [x] Python/PySide6 desktop application entry point.
- [x] Layered application package structure.
- [x] Local SQLite persistence for transactions and imported-file history.
- [x] JSON-backed application settings and merchant/category rules.
- [x] PDF text extraction and initial supported-bank import paths.
- [x] Recursive finance-folder synchronization and duplicate detection by file hash.

## Version 0.2: Transaction Management

- [x] Display stored transactions in the main table.
- [x] Sort by date, merchant, category, and amount through SQLite ordering.
- [x] Default to newest-first date ordering.
- [x] Live, case-insensitive partial search over persisted merchant and category values.
- [x] Preserve the active sort during search and table reloads.
- [x] Add SQLite-backed date, category, and amount filters that compose with search and sorting.
- [ ] Define and complete persistence behavior for individual transaction edits.
- [ ] Add a reviewed SQLite migration for payment method and transaction type, then expose those fields to search.
- [ ] Add transaction deletion and other editing workflows with explicit data-safety behavior.

## Version 0.3: Learning Categorization

- [x] Initial merchant keyword categorization.
- [x] User-managed merchant/category rules and custom category management.
- [ ] Improve rule precedence, normalization, and explainability.
- [x] Persist learned merchant-category rules in SQLite and apply them to future imports.
- [ ] Add user feedback or correction workflows that can be reliably persisted.
- [ ] Add regression tests for learned-rule matching and updates.

### Sprint 8.6

- [x] 8.6.1 Persist merchant rules and automatically categorize matching imports.
- [x] 8.6.2 Review unknown transactions in a batch, save individual or batch categories, and optionally learn merchant rules.
- [x] 8.6.2.1 Apply explicitly saved learning rules to exact merchant matches that are still uncategorized, preserving existing categories.
- [ ] 8.6.3 Suggest categories for unknown merchants.
- [ ] 8.6.4 Normalize merchant names conservatively.
- [ ] 8.6.5 Support persisted manual exceptions and rule management.
- [ ] 8.6.6 Complete import integration and validation.

## Version 0.4: Budgets

- [ ] Define budget periods, category allocation, and rollover rules.
- [ ] Persist budgets with a versioned storage design.
- [ ] Add budget entry and editing workflows.
- [ ] Compare actual spending with budget targets.

## Version 0.5: Reports

- [ ] Define report requirements and supported date ranges.
- [ ] Add category, merchant, and period summaries.
- [ ] Add export formats and verify locale-aware dates and amounts.
- [ ] Add report tests using controlled transaction fixtures.

## Version 0.6: Dashboard

- [ ] Identify the key household finance metrics and their definitions.
- [ ] Add a dashboard based on verified report/service queries.
- [ ] Support useful period comparisons without duplicating business logic in widgets.
- [ ] Validate loading and empty-data states.

## Future Ideas

- [ ] Expand supported financial institutions and import formats.
- [ ] Add recurring transaction detection.
- [ ] Add configurable data backup and restore.
- [ ] Review accessibility, localization, packaging, and release workflows as the application matures.