"""pipeline-003 — natural language query → filtered CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
TRANSACTIONS = HERE / "transactions.csv"
QUERY = HERE / "query.txt"
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

    if len(actual) != len(expected):
        return False, f"row count: got {len(actual)}, want {len(expected)}"

    if len(expected) == 0 and len(actual) == 0:
        return True, "ok"

    # Sort both for stable comparison
    sort_cols = [c for c in ["date", "transaction_id"] if c in actual.columns]
    if sort_cols:
        actual = actual.sort_values(sort_cols).reset_index(drop=True)
        expected = expected.sort_values(sort_cols).reset_index(drop=True)

    # Check transaction_ids match
    if "transaction_id" in actual.columns and "transaction_id" in expected.columns:
        if set(actual["transaction_id"]) != set(expected["transaction_id"]):
            return False, (
                f"wrong transactions: got {sorted(actual['transaction_id'])}, "
                f"want {sorted(expected['transaction_id'])}"
            )

    try:
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, atol=0.01)
    except AssertionError as e:
        return False, f"data mismatch: {e}"
    return True, "ok"


TASK = register(
    Task(
        id="pipeline-003",
        group="pipeline",
        description=(
            "You have two files:\n"
            "- `transactions.csv`: columns transaction_id, date, category, type, amount\n"
            "- `query.txt`: a natural language query describing which transactions to select.\n\n"
            "Task:\n"
            "1. Read the query from `query.txt`.\n"
            "2. Interpret the natural language conditions and apply them as filters on "
            "the transactions data.\n"
            "3. Write the matching rows to `output.csv` with all original columns. "
            "Sort by date ascending.\n\n"
            "Hint: the query will reference date ranges (like 'Q3 2024'), amount thresholds, "
            "categories, and transaction types (purchase/refund). Parse these carefully."
        ),
        input_files=(TRANSACTIONS, QUERY),
        expected_path=EXPECTED,
        accept=accept,
    )
)
