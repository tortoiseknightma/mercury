"""json-002 — nested JSON → flatten with dotted keys to CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
INPUT = HERE / "input.json"
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
        id="json-002",
        group="json",
        description=(
            "`input.json` contains a JSON array of nested objects. Flatten each "
            "object so nested fields use a dotted column name (`user.name`, "
            "`user.address.city`, etc.) and write the result to `output.csv`. "
            "Use the column order: id, user.name, user.address.city, "
            "user.address.country, score. Hint: pandas `json_normalize` does "
            "this with `sep='.'`."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
