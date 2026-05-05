"""csv-005 — mixed line endings (CRLF / LF / CR) and scattered blank lines."""

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
    # Reject blank lines anywhere in the file (including a leading one).
    text = raw.decode("utf-8")
    # Normalise to LF for the empty-line check, but require the actual file
    # to use a single, consistent line ending (LF or CRLF, not mixed).
    if "\r\n" in text and "\n" in text.replace("\r\n", ""):
        return False, "output.csv has mixed line endings"
    if "\r" in text.replace("\r\n", "").replace("\n", ""):
        return False, "output.csv contains stray CR characters"
    normalized = text.replace("\r\n", "\n").rstrip("\n")
    if any(line.strip() == "" for line in normalized.split("\n")):
        return False, "output.csv still contains blank lines"

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
        id="csv-005",
        group="csv",
        description=(
            "`input.csv` has been concatenated from several sources: it uses a "
            "MIX of CRLF, LF, and bare CR line terminators, and contains "
            "blank lines scattered between data rows. Produce a clean "
            "`output.csv` with consistent line endings (use LF) and no blank "
            "lines. Column order, header row, and data values must match "
            "the input exactly (after dropping blanks)."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
