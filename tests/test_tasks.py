"""Task registry sanity checks.

For every registered task we verify:
  - task.py defined the expected fields
  - input file(s) exist
  - expected file exists and is readable as CSV
  - acceptance check fails (correctly) on an empty workspace
  - acceptance check passes when we copy the expected file in as output.csv
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from mercury.eval.tasks import all_tasks


@pytest.mark.parametrize("task", all_tasks(), ids=lambda t: t.id)
def test_task_files_present(task) -> None:
    for f in task.input_files:
        assert f.exists(), f"missing input: {f}"
    assert task.expected_path.exists(), f"missing expected: {task.expected_path}"


@pytest.mark.parametrize("task", all_tasks(), ids=lambda t: t.id)
def test_expected_is_readable_csv(task) -> None:
    df = pd.read_csv(task.expected_path)
    assert len(df) > 0, "expected has zero rows"
    assert len(df.columns) > 0


@pytest.mark.parametrize("task", all_tasks(), ids=lambda t: t.id)
def test_accept_rejects_empty_workspace(task, tmp_path: Path) -> None:
    passed, _reason = task.accept(tmp_path)
    assert not passed, "accept must fail when output.csv is missing"


@pytest.mark.parametrize("task", all_tasks(), ids=lambda t: t.id)
def test_accept_passes_with_expected_as_output(task, tmp_path: Path) -> None:
    """Pour the ground-truth file in as `output.csv` — accept should pass.

    This proves the acceptance check isn't impossibly strict.
    """
    shutil.copy(task.expected_path, tmp_path / "output.csv")
    passed, reason = task.accept(tmp_path)
    assert passed, f"accept rejected the ground truth: {reason}"
