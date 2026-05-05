"""log-002 — extract Python tracebacks from a mixed log → CSV one row per traceback."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
INPUT = HERE / "app.log"
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
        id="log-002",
        group="log",
        description=(
            "`app.log` contains a mix of regular log lines and multi-line "
            "Python tracebacks (each starting with the literal line "
            "`Traceback (most recent call last):` and ending with the "
            "exception summary line, e.g. `ValueError: bad input`). "
            "Find every traceback in the file and write `output.csv` with "
            "ONE row per traceback and EXACTLY these columns: timestamp, "
            "exception_type, message. The `timestamp` is the timestamp "
            "from the log line *immediately preceding* the `Traceback` "
            "marker (format: `2024-10-10 13:55:36`). The exception_type "
            "and message come from splitting the final `<Type>: <message>` "
            "line on the FIRST `: ` only. Order rows by file appearance."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
