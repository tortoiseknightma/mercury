"""multi-002 — multi-table JOIN with currency conversion and aggregation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
ORDERS = HERE / "orders.csv"
PRODUCTS = HERE / "products.csv"
RATES = HERE / "exchange_rates.json"
EXPECTED = HERE / "expected.csv"


def accept(workspace: Path) -> tuple[bool, str]:
    out = workspace / "output.csv"
    if not out.exists():
        return False, "output.csv missing"
    try:
        actual = pd.read_csv(out)
    except Exception as e:
        return False, f"output.csv unreadable: {e}"
    expected = pd.read_csv(EXPECTED)

    if list(actual.columns) != list(expected.columns):
        return False, f"columns: got {list(actual.columns)}, want {list(expected.columns)}"

    actual = actual.sort_values("category").reset_index(drop=True)
    expected = expected.sort_values("category").reset_index(drop=True)

    try:
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, atol=0.5)
    except AssertionError as e:
        return False, f"data mismatch: {e}"
    return True, "ok"


TASK = register(
    Task(
        id="multi-002",
        group="multi",
        description=(
            "You have three files:\n"
            "- `orders.csv`: columns order_id, product_id, amount, currency, order_date\n"
            "- `products.csv`: columns product_id, product_name, category\n"
            "- `exchange_rates.json`: a dict mapping date strings to {currency: rate_to_usd}.\n\n"
            "Task:\n"
            "1. Convert each order's amount to USD using the exchange rate for that order_date. "
            "If the exact date is not in the rates table, use the closest earlier date.\n"
            "2. JOIN with products.csv to get each order's category.\n"
            "3. Aggregate by category: compute total_usd (sum, rounded to 2 decimals) and order_count.\n"
            "4. Write `output.csv` with columns: category, total_usd, order_count. Sort by category."
        ),
        input_files=(ORDERS, PRODUCTS, RATES),
        expected_path=EXPECTED,
        accept=accept,
    )
)
