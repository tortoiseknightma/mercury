"""Per-task workspace setup.

A workspace is a fresh directory on the host containing the task's input
files. It is bind-mounted into the Docker sandbox at /workspace, and the
agent is told to write its answer (e.g. output.csv) inside it. Acceptance
checks read the workspace from the host side after `submit`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from mercury.config import RESULTS_DIR
from mercury.eval.tasks import Task


WORKSPACES_DIR = RESULTS_DIR / "workspaces"


def prepare(task: Task, *, run_label: str) -> Path:
    """Create a fresh workspace for a task run; return its path."""
    ws = WORKSPACES_DIR / f"{task.id}__{run_label}"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    for src in task.input_files:
        shutil.copy(src, ws / src.name)
    return ws


def cleanup(workspace: Path) -> None:
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
