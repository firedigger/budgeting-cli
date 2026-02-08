# Budgeting CLI

A small CLI for importing bank transaction records and interactively categorizing them, so you can see in reports how much went where. There are probably full-on budgeting tools that support this, but I wanted a dumb, simple, fast CLI tool, so I vibe-coded one.

## CLI snapshot

### Category picker

```text
╭──────── Transaction ─────────╮
│ Date     2026-01-19 (booked) │
│ Amount   20.00 EUR (EUR)     │
│ Name     CARD*GROCERY STORE  │
│ Message  HELSINKI            │
│ Ref      1234567890          │
╰──────────────────────────────╯
? Pick category + remember? (Use shortcuts or arrow keys)
 »   Shared (remember vendor)
	 Shared (remember vendor + amount)
	 Shared (ask next time)
	 Alex (remember vendor)
	 Alex (remember vendor + amount)
	 Alex (ask next time)
	 Luiza (remember vendor)
	 Luiza (remember vendor + amount)
	 Luiza (ask next time)
	 Skip this transaction (ignore in reports)
	 Skip this transaction (ignore in reports) + remember vendor
	 Skip for now (move to unsorted, keep going)
	 Back to menu / stop now (rest -> unsorted)
```

### Report

```text
? Period: (Use shortcuts or arrow keys)
	 Week
	 Month
	 Year
 »   All
	 Past 7d
	 Past 30d
	 Back

	Expenses by category (all time)
┏━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Category ┃        Spend ┃   Pct ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━┩
│ shared   │ 3 000.00 EUR │ 66.7% │
│ luiza    │   980.00 EUR │ 19.6% │
│ alex     │   970.00 EUR │ 19.4% │
│ unsorted │    50.00 EUR │  1.0% │
└──────────┴──────────────┴───────┘
```

## Background

In a married household with combined income, expenses are usually shared or someone's personal. I wanted to estimate each person's share of total expenses, and I wanted a fast, minimal-clicks workflow, but with patterns that save time. For example, the mortgage payment is always shared; some vendors are always my expenses; and some are always my wife's. For other vendors, typical purchases can be remembered via a vendor + amount rule. Some transactions are refunds and can be ignored in reports, and anything can be saved for later as unsorted.

## Setup

This project runs with your system Python.

Install dependencies (global or user):

```powershell
python -m pip install -r requirements.txt
```

If you prefer a user install:

```powershell
python -m pip install --user -r requirements.txt
```

## Usage

Use the menu (recommended):

```powershell
./budget.ps1
```

## Storage

Creates `budgeting.sqlite` in the current directory.

## Tests

Install test dependencies:

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
```

Run:

```powershell
python -m pytest -q
```

## Customization

To support another import format or categories, you can change the code or easier you can use any AI in the repo to help you. More detailed guidance is in `agents.md`.

## TODO
