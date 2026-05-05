"""xml-002 — broken/malformed XML (RSS feed) repair + extraction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
INPUT = HERE / "broken_feed.xml"
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

    if len(actual) != len(expected):
        return False, f"row count: got {len(actual)}, want {len(expected)}"

    # Compare row by row with tolerance for whitespace in descriptions
    for i in range(len(expected)):
        for col in expected.columns:
            exp_val = str(expected.iloc[i][col]).strip()
            act_val = str(actual.iloc[i][col]).strip()
            if exp_val != act_val:
                return False, f"row {i}, col '{col}': got '{act_val[:80]}', want '{exp_val[:80]}'"

    return True, "ok"


TASK = register(
    Task(
        id="xml-002",
        group="xml",
        description=(
            "`broken_feed.xml` is a malformed RSS feed with multiple issues:\n"
            "- UTF-8 BOM at the start of the file\n"
            "- An unclosed `<link>` tag (missing `</link>`) in one item\n"
            "- Mixed HTML entities (`&mdash;`, `&amp;`, `&apos;`) alongside CDATA sections\n\n"
            "Your task:\n"
            "1. Read the file and handle/repair the XML errors (consider using a tolerant "
            "parser like BeautifulSoup with 'lxml-xml' or 'html.parser').\n"
            "2. Extract all `<item>` elements.\n"
            "3. For each item, extract: title, link, pub_date (from pubDate), description.\n"
            "4. In description, strip ALL HTML/XML tags (keep only plain text). "
            "Decode HTML entities (`&mdash;` → —, `&amp;` → &, etc.).\n"
            "5. Write `output.csv` with columns: title, link, pub_date, description."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
