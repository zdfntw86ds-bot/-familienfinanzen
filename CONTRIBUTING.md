# Contributing

This guide describes the expected development workflow for FamilienFinanzen. See [AGENTS.md](AGENTS.md) for instructions that also apply to AI coding agents, [ARCHITECTURE.md](ARCHITECTURE.md) for module ownership, [ROADMAP.md](ROADMAP.md) for planned work, and [CHANGELOG.md](CHANGELOG.md) for completed changes.

## Branch Strategy

- Use a short-lived branch for each feature, fix, or documentation change.
- Name branches clearly, for example `feat/transaction-search` or `fix/postfinance-date`.
- Keep pull requests focused and avoid bundling unrelated refactoring.

## Commit Style

Use short imperative commit subjects, optionally with a Conventional Commit type and scope:

```text
feat(search): add category filtering
fix(sync): preserve import history on duplicate files
docs: clarify database ownership
```

Do not commit generated databases, private finance data, credentials, or unrelated user changes.

## Sprint Workflow

1. Confirm the goal, constraints, and observable acceptance criteria.
2. Inspect the owning module, nearby tests, and current repository state.
3. State the implementation hypothesis and a focused check before editing.
4. Implement the smallest change in the layer that owns the behavior.
5. Add or update tests, run the focused check, then run the full suite when appropriate.
6. Review the diff and update documentation where behavior or project direction changed.
7. Report changed files, tests, results, and known limitations.

## Testing Requirements

- Use Python's `unittest` framework and keep tests deterministic.
- Use temporary files/directories and temporary SQLite databases for import, persistence, and query tests.
- Add regression tests for bug fixes and focused tests for new behavior.
- For UI wiring, use Qt's offscreen platform where a display is not available; avoid testing business logic only through widget interactions.
- Run the relevant test module first and then:

  ```bash
  python -m unittest discover -v
  ```

- Do not modify or weaken unrelated tests to accommodate a feature.

## Review Checklist

- Does the change meet the acceptance criteria and respect explicit restrictions?
- Is the implementation in the correct layer?
- Are SQL values parameterized and dynamic identifiers allowlisted?
- Are dates, amount signs, duplicate detection, and existing user data preserved?
- Are edge cases covered by focused tests?
- Are docs accurate about what is implemented versus planned?
- Does the diff contain only intentional files and no generated/private data?

## Coding Conventions

- Follow PEP 8 and the surrounding code's naming and formatting patterns.
- Prefer descriptive names, narrow functions, and practical type annotations.
- Keep dependencies and abstractions to the minimum needed for the behavior.
- Keep comments focused on non-obvious reasoning.
- Separate UI, service/workflow, importer, model, and persistence concerns.

## Architecture Rules

- UI modules coordinate interaction and presentation; they should not own SQL or bank-format parsing.
- Importers parse source documents into domain data and should not control UI or import-history policy.
- Services own application workflows and persistence access.
- Models describe domain values but do not guarantee that every field is persisted.
- Keep new financial calculations out of widgets; reporting calculations should live in testable services or domain functions.

## Database and Schema Changes

Schema changes are allowed only when the feature explicitly requires them and the change has been reviewed. Include a migration or safe initialization strategy for existing databases, preserve user data, and add tests for both new and pre-existing database states. Never hand-edit or commit `data/finance.db` as a substitute for a migration. Until such a change is approved, query only fields that are actually persisted.

## Adding a Feature

- Identify its owning layer and public interface before implementation.
- Extend existing services and patterns when they fit; avoid parallel implementations.
- For imports, add an isolated parser with representative fixtures and edge-case coverage.
- For SQL-backed table features, implement filtering/order in SQLite, validate identifiers, bind values, and preserve view state on reload.
- Update `AGENTS.md`, `ARCHITECTURE.md`, `ROADMAP.md`, or `CHANGELOG.md` only where their long-term guidance or factual state changes.

## AI-Assisted Contributions

AI agents should read [AGENTS.md](AGENTS.md) first, inspect the current code rather than infer behavior from roadmap notes, and preserve all user changes. They should make narrow edits, run executable validation, avoid inventing features or data fields, and report limitations plainly. Agents must not commit or modify unrelated files unless asked.