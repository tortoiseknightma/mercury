"""multi-001 — merge GBK + UTF-8 CSVs, apply JSON corrections, deduplicate."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
SALES_2023 = HERE / "sales_2023.csv"
SALES_2024 = HERE / "sales_2024.csv"
CORRECTIONS = HERE / "corrections.json"
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

    # Normalize column names for comparison
    actual.columns = [c.strip().lower() for c in actual.columns]
    expected.columns = [c.strip().lower() for c in expected.columns]

    if set(actual.columns) != set(expected.columns):
        return False, f"columns: got {sorted(actual.columns)}, want {sorted(expected.columns)}"

    # Reorder columns to match expected
    actual = actual[list(expected.columns)]

    # Sort by order_id for stable comparison
    actual = actual.sort_values("order_id").reset_index(drop=True)
    expected = expected.sort_values("order_id").reset_index(drop=True)

    if len(actual) != len(expected):
        return False, f"row count: got {len(actual)}, want {len(expected)} (dedup needed?)"

    try:
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, atol=0.01)
    except AssertionError as e:
        return False, f"data mismatch: {e}"
    return True, "ok"


TASK = register(
    Task(
        id="multi-001",
        group="multi",
        description=(
            "You have three files:\n"
            "- `sales_2023.csv`: Sales data from 2023, encoded in **GBK** (Chinese characters). "
            "Contains duplicate rows that must be removed.\n"
            "- `sales_2024.csv`: Sales data from 2024, UTF-8 encoded. Column names use "
            "different casing (e.g. `Order_ID` vs `order_id`).\n"
            "- `corrections.json`: A JSON array of correction records, each with "
            "`order_id`, `field`, and `new_value`. Apply these corrections to the merged data.\n\n"
            "Merge both CSVs into a single `output.csv` with unified lowercase column names "
            "(order_id, product, quantity, unit_price, date). Remove duplicates, apply the "
            "JSON corrections, and sort by order_id ascending."
        ),
        input_files=(SALES_2023, SALES_2024, CORRECTIONS),
        expected_path=EXPECTED,
        accept=accept,
    )
)
