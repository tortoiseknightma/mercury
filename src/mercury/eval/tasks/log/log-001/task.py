"""log-001 — nginx combined access log → structured CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
INPUT = HERE / "access.log"
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
        id="log-001",
        group="log",
        description=(
            "`access.log` contains nginx access entries in the *combined* log "
            "format: \n"
            "  `<ip> - - [<date>] \"<method> <path> <proto>\" <status> <bytes> ...`\n"
            "Parse every line and write `output.csv` with EXACTLY these columns "
            "(in this order): ip, datetime, method, path, status, bytes. "
            "Keep `datetime` as the raw bracketed string from the log "
            "(e.g. `10/Oct/2024:13:55:36 +0000`). status and bytes must be "
            "integers."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
