"""pipeline-001 — anomaly detection on sensor time series using Z-score."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mercury.eval.tasks import Task, register


HERE = Path(__file__).parent
INPUT = HERE / "sensor_readings.csv"
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

    if "is_anomaly" not in actual.columns:
        return False, "missing 'is_anomaly' column"

    if len(actual) != len(expected):
        return False, f"row count: got {len(actual)}, want {len(expected)}"

    # Convert is_anomaly to bool
    actual_flags = actual["is_anomaly"].astype(str).str.strip().str.lower()
    actual_flags = actual_flags.map({"true": True, "false": False, "1": True, "0": False})
    expected_flags = expected["is_anomaly"].astype(bool)

    actual_count = actual_flags.sum()
    expected_count = expected_flags.sum()

    # Allow some tolerance: anomaly count must match exactly
    if actual_count != expected_count:
        return False, f"anomaly count: got {actual_count}, want {expected_count}"

    # Check that the anomaly positions match
    mismatches = (actual_flags != expected_flags).sum()
    if mismatches > 0:
        return False, f"{mismatches} rows have wrong is_anomaly labels"

    return True, "ok"


TASK = register(
    Task(
        id="pipeline-001",
        group="pipeline",
        description=(
            "`sensor_readings.csv` contains 200 rows of time-series sensor data with columns "
            "`timestamp` and `value`. The data has a baseline around 100 with normal noise, "
            "but contains anomalous spikes and drifts.\n\n"
            "Task:\n"
            "1. Read the sensor data.\n"
            "2. Detect anomalies using the **Z-score method**: any value where "
            "|value - mean| > 3 * std_dev is an anomaly.\n"
            "3. Add a boolean column `is_anomaly` (True/False) to the data.\n"
            "4. Write `output.csv` with all original columns plus the new `is_anomaly` column."
        ),
        input_files=(INPUT,),
        expected_path=EXPECTED,
        accept=accept,
    )
)
