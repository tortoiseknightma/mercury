"""csv-001 — European-style CSV → US-style CSV (semicolon + comma-decimal + BOM)."""

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
        return False, f"output.csv unreadable as standard CSV: {e}"

    expected = pd.read_csv(EXPECTED)

    if list(actual.columns) != list(expected.columns):
        return False, f"columns mismatch: got {list(actual.columns)}, want {list(expected.columns)}"

    try:
        pd.testing.assert_frame_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=False,
        )
    except AssertionError as e:
        return False, f"data mismatch: {e}"

    # Reject BOM in the output.
    raw = out.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False, "output.csv still contains a UTF-8 BOM"

    return True, "ok"


TASK = register(
    Task(
        id="csv-001",
        group="csv",
        description=(
            "The file `input.csv` was exported from a European spreadsheet: "
            "semicolon-delimited, comma as decimal separator, and a UTF-8 BOM. "
            "Convert it to standard US-style CSV (comma-delimited, period-decimal, "
            "no BOM) and write it as `output.csv` in the same directory. "
            "Preserve the column order and row order exactly."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
