"""pipeline-002 — time series alignment + linear interpolation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
STATION_A = HERE / "station_a.csv"
STATION_B = HERE / "station_b.csv"
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

    required_cols = ["timestamp", "a_value", "b_value", "diff"]
    for c in required_cols:
        if c not in actual.columns:
            return False, f"missing column: {c}"

    if len(actual) != len(expected):
        return False, f"row count: got {len(actual)}, want {len(expected)}"

    # Compare numeric columns with tolerance
    for col in ["a_value", "b_value", "diff"]:
        try:
            act_vals = actual[col].astype(float)
            exp_vals = expected[col].astype(float)
        except Exception:
            return False, f"column {col} is not numeric"
        max_diff = (act_vals - exp_vals).abs().max()
        if max_diff > 0.5:
            return False, f"column {col}: max deviation = {max_diff:.2f} (tolerance 0.5)"

    return True, "ok"


TASK = register(
    Task(
        id="pipeline-002",
        group="pipeline",
        description=(
            "You have two time-series files from different sensors:\n"
            "- `station_a.csv`: sampled every **5 minutes** (columns: timestamp, value)\n"
            "- `station_b.csv`: sampled every **7 minutes** with some missing intervals "
            "(columns: timestamp, value)\n\n"
            "Task:\n"
            "1. Align both series to a unified **1-minute** time grid from the earliest to "
            "latest timestamp across both files.\n"
            "2. Use **linear interpolation** to fill in the gaps for each station.\n"
            "3. Compute a difference column: `diff = a_value - b_value`.\n"
            "4. Write `output.csv` with columns: timestamp, a_value, b_value, diff. "
            "Sort by timestamp ascending. Round all numeric values to 2 decimal places."
        ),
        input_files=(STATION_A, STATION_B),
        expected_path=EXPECTED,
        accept=accept,
    )
)
