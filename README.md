# Sales pipeline

## Setup & run

Needs Python 3.13+ and uv. If you do not use UV, install it with `pip install uv`.

    uv sync               # create .venv and install deps
    uv run pipeline.py    # main pipeline run
    uv run pytest         # run all tests

Tests:
- `test_virtual_column.py`: sample tests from the task (unchanged)
- `test_solution.py`: extra tests for `add_virtual_column`
- `test_pipeline.py`: one test per cleaning step, an end-to-end run on a small made-up file, and a snapshot test on the real `sales.csv`

## add_virtual_column

- The new column name and every name in `role` may only contain letters and `_`.
- `role` can only be column names joined by `+`, `-` or `*`. No numbers, brackets or other operators.
- If the name is bad, the expression is bad or a column doesn't exist, the function returns an empty DataFrame.
- The input DataFrame is never changed; the function works on a copy.
- Each name is put in backticks before `df.eval`, so columns named like `True` or `and` are read as columns, not Python.
- Only numeric columns are supported; a text column in `role` raises a `TypeError` instead of returning an empty DataFrame.
- The spec is unclear in two places, so: the new column gets exactly the name passed in (the example passes `total` but shows `price_total`), and only the column labels used in `role` are validated, not every column in `df`.

## Assumptions

- **Negative quantities are product returns** and give negative revenue. The footer quantity total only matches if they stay negative.
- **Discount** is money off the whole line, not per unit, so revenue = `quantity * unit_price - discount`. An empty discount means 0.
- **Revenue is rounded to 2 decimal places per line**, then summed per region.
- **Duplicates** are exact copies of a line, compared *after* cleaning, so two copies that differ only in spaces or capitals still count. The footer check runs *before* removing duplicates, because the footer total includes them. They are still dropped because every other order ID appears on exactly one line, so a repeated ID is an export error, not a real second line.
- **Missing unit price** is filled from the product's price, but ONLY if that product has exactly one known price. Products with more than one price are logged and not used to fill.
- **Missing region** becomes `Unknown`, so the revenue isn't lost (this file has none).
- **Big quantities** (e.g. 1 371) are real big orders. The footer total agrees with them.
- **Order date** isn't needed for revenue, so a bad date becomes `NaT` and the row stays.
- Output sorted by revenue, highest first.

## Problems found in sales.csv

1 507 rows read, 1 500 clean order lines out.

- **Header `Quantity ` has a trailing space, headers aren't snake_case** (header only): renamed all columns to snake_case; fail if a column is missing.
- **Header row repeated in the middle of the file** (1 row): dropped, since its order ID doesn't match `SO-<number>`.
- **`TOTAL` footer row** (1 row): read the quantity/discount totals for a check, then dropped.
- **Region with mixed case / extra spaces** (`EAST`, ` South`, `west  `) (15 rows): trimmed, collapsed spaces, title case.
- **Quantity with a thousands separator** (`1 762`) (4 rows): removed the space, kept as a big order.
- **Negative quantity** (6 rows): kept as returns (see assumptions).
- **Unit price with a decimal comma** (`39,90`) (7 rows): comma → dot.
- **Missing unit price** (2× Printer paper, 2× Keyboard) (4 rows): filled from the product's only known price.
- **Empty discount** (963 rows): set to 0.
- **Exact duplicate lines** (SO-10305, SO-10822, SO-10966, SO-11240, SO-11405) (5 rows): dropped after the footer check.

Footer check: quantity (37 150) and discount (65 924.67) sums match the footer.

**Also handled, 0 rows in this file:** non-`SO-` order IDs (dropped + warned), zero or non-numeric quantity (dropped), badly formatted price (set missing, then filled if possible), non-numeric discount (dropped), missing price with no single known product price (dropped), missing region (`Unknown`), bad date (`NaT`, row kept). Every case is logged when it happens.
