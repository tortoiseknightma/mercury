"""csv-003 — thousand separators inside quoted numeric strings."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
INPUT = HERE / "input.csv"
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
    # Compare as numeric where applicable.
    for col in ("revenue", "units"):
        if not pd.api.types.is_numeric_dtype(actual[col]):
            return False, f"column `{col}` is not numeric in output (got dtype {actual[col].dtype})"
    try:
        pd.testing.assert_frame_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=False,
        )
    except AssertionError as e:
        return False, f"data mismatch: {e}"
    return True, "ok"


TASK = register(
    Task(
        id="csv-003",
        group="csv",
        description=(
            "`input.csv` contains numeric columns (`revenue`, `units`) where "
            "values are quoted strings using comma as a thousand separator "
            "(e.g. `\"1,234,567\"`). Produce `output.csv` with the same columns "
            "where these values are stored as plain numbers (no commas, no "
            "quotes), suitable for arithmetic in pandas. The text columns "
            "must be preserved as-is."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
