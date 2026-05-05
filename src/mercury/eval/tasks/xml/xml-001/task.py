"""xml-001 — namespaced XML catalog → flat CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
INPUT = HERE / "catalog.xml"
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
        id="xml-001",
        group="xml",
        description=(
            "`catalog.xml` is an XML file with **XML namespaces** "
            "(prefix `bk` for books, `pub` for publisher). Each `<bk:book>` element has:\n"
            "- An `isbn` attribute\n"
            "- Child elements: title, author/name, author/nationality, publisher, price, year\n\n"
            "Parse the XML (handling namespaces correctly) and write `output.csv` with columns "
            "(in this exact order): isbn, title, author_name, author_nationality, publisher, "
            "price, year. The `price` should be a float and `year` an integer."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
