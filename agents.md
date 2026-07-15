# Agents Notes (Repo Context)

This file captures context for agents (and future maintainers) so changes stay consistent with the original goals.

## Privacy before publishing

Before staging, committing, or pushing, review the complete intended diff for personal information.

- Do not version real income amounts, transaction data, account details, generated financial charts, or specific geography below country level.
- Keep local databases, configuration files, bank exports, and generated charts ignored by Git.
- Use clearly synthetic financial values in tests and documentation.

## What this project is

A local-first, interactive CLI for budgeting from bank CSV exports.

Core workflow:
- Import a bank CSV export
- Dedupe already-ingested transactions
- Categorize expenses into: `shared`, `alex`, `luiza`
- Optionally remember categorization rules to reduce prompts
- Allow deferring items to `unsorted` and sorting later
- Support `skip` (ignored in reports) for noise transactions
- Produce period summaries and a “largest transactions” view

Storage:
- SQLite file `budgeting.sqlite` in the current working directory
- Do not delete or wipe an existing `budgeting.sqlite` unless the user explicitly asks for it.

Key invariants:
- Expenses-only: only rows with `amount_cents < 0` are stored/considered.
- Dedupe: fingerprint is `UNIQUE` in SQLite; imports use `INSERT OR IGNORE`.
- Ignored: `ignored=1` excludes rows from reports and unsorted sorting.

## How dedupe works (fingerprint)

Today the “real” spend categories are hard-coded to `shared`, `alex`, `luiza`.

Related statuses:
- `unsorted` is a temporary bucket for “decide later” (still included in reports).
- `skip` is implemented as `ignored=1` in the DB (excluded from reports and unsorted sorting).

If you want to rename categories (e.g. `alex` -> `me`) or add/remove categories:

1) Update the DB constraints
- Schema CHECK constraints currently enforce allowed values in:
  - [src/budgeting_cli/db.py](src/budgeting_cli/db.py) (`vendor_rules`, `vendor_amount_rules`, and `transactions.category`)
- Easiest path is to wipe the DB after changes:
  - Run the “Reset (wipe all data)” menu item, or delete `budgeting.sqlite` in your working directory.
  - If you need to keep existing data, you’ll need a real migration (SQLite can’t easily change CHECK constraints in-place).

2) Update the interactive prompts and menus
- Import/sort prompt choices are defined in:
  - [src/budgeting_cli/ui.py](src/budgeting_cli/ui.py)
- Category filters + edit-mode statuses are defined in:
  - [src/budgeting_cli/menu.py](src/budgeting_cli/menu.py)

3) Update reporting assumptions
- Report code currently “pins” expected categories to always exist (and orders them) in:
  - [src/budgeting_cli/commands/report_cmd.py](src/budgeting_cli/commands/report_cmd.py)

4) Update import/sort assertions
- There are explicit assertions that categories are one of `shared/alex/luiza` in:
  - [src/budgeting_cli/commands/import_cmd.py](src/budgeting_cli/commands/import_cmd.py)
  - [src/budgeting_cli/commands/sort_unsorted_cmd.py](src/budgeting_cli/commands/sort_unsorted_cmd.py)

5) Update tests
- Several tests assume the default category set; adjust accordingly in:
  - [tests](tests)
Each imported row is normalized and hashed into a fingerprint.

Current Nordea fingerprint inputs (see `src/budgeting_cli/nordea_csv.py`):
- booking_date_raw_norm ("YYYY/MM/DD" or the literal "Reserved")
- amount_cents
- currency
- sender, recipient
- name, title, message
- reference_number

Notes:
- Reserved rows use `booking_date = import_day` for display/reporting, but fingerprint uses the literal `"Reserved"` so re-importing on a different day still dedupes.
- If the bank changes message/title/reference formatting between exports, the fingerprint may change and the row will be treated as new.

## Rules (to reduce prompting)

Rules are applied in this order:
1) Ignore-vendor rules (`ignore_vendor_rules`): auto-set `ignored=1`
2) Vendor+amount rules (`vendor_amount_rules`): match on `(vendor_key, amount_cents, currency)`
3) Vendor rules (`vendor_rules`): match on `vendor_key`

## Switching / Adding a new bank provider

CSV import goes through header auto-detection in:
- [src/budgeting_cli/bank_csv.py](src/budgeting_cli/bank_csv.py)

Current provider parsers:
- Nordea: [src/budgeting_cli/nordea_csv.py](src/budgeting_cli/nordea_csv.py)
- EntryDate export format: [src/budgeting_cli/entrydate_csv.py](src/budgeting_cli/entrydate_csv.py)

To add another bank:

1) Create a new parser module
- Add `src/budgeting_cli/<bank>_csv.py`.
- Implement a function like:

  `read_<bank>_rows(csv_path: Path, *, import_day: date | None = None) -> list[ImportedRow]`

  Reuse the generic `ImportedRow` dataclass from `src/budgeting_cli/imported_row.py`.

2) Ensure the parser produces consistent normalized fields
- `amount_cents` must be integer cents, negative for expenses.
- `currency` should be a 3-letter code.
- `vendor_key` should be a stable, normalized vendor identifier (use `normalize_vendor_key`).
- `fingerprint` must be deterministic and stable across re-imports.

3) Wire it into imports
- Add the expected headers and reader to `src/budgeting_cli/bank_csv.py`.
- Prefer header auto-detection. Ask the user only if formats become ambiguous or detection fails.
- Keep the normalization contract identical so DB schema and the rest of the app doesn’t change.

## Where to extend behavior safely

- Reporting totals logic: `src/budgeting_cli/commands/report_cmd.py` (`get_expense_totals_by_category`).
- Transaction listing: `src/budgeting_cli/commands/list_transactions_cmd.py`.
- Interactive categorization prompt: `src/budgeting_cli/ui.py`.
- Import loop (rules, dedupe, unsorted): `src/budgeting_cli/commands/import_cmd.py`.

## Tests

Tests are in `tests/` and use `pytest`.

They specifically cover:
- Dedupe on re-import (no effect)
- Vendor rules and vendor+amount rules
- Ignore vendor rule behavior
- Reserved row fingerprint stability
- Edit-state DB update helper
