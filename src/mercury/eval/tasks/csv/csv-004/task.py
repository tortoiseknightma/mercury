"""csv-004 — UTF-16 LE input → UTF-8 output."""

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

    raw = out.read_bytes()
    # Reject any UTF-16 / UTF-8 BOMs.
    if raw.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return False, "output.csv must not contain a BOM"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return False, f"output.csv is not valid UTF-8: {e}"

    try:
        actual = pd.read_csv(out)
    except Exception as e:
        return False, f"output.csv unreadable: {e}"
    expected = pd.read_csv(EXPECTED)
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
        id="csv-004",
        group="csv",
        description=(
            "`input.csv` was saved by a Windows application using UTF-16 LE "
            "encoding (with a UTF-16 BOM). Re-encode it as UTF-8 (no BOM) "
            "and write the result to `output.csv`, preserving columns and "
            "data exactly. The output must be valid UTF-8 with no byte-order "
            "mark."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
