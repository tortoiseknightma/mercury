"""Evaluation task registry.

Each subpackage (csv/, json/, log/) contains task directories. Each task
directory has:

    task.py         -- defines `TASK = Task(...)` and an `accept(workspace)` callable
    input.<ext>     -- input file (copied into the agent's workspace at run time)
    expected.<ext>  -- ground truth (kept on the host, never exposed to the agent)

The acceptance check is a deterministic Python function — never an LLM judge —
so the self-evolution loop has a stable reward signal.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from mercury.config import EVAL_TASKS_DIR


@dataclass(frozen=True)
class Task:
    id: str
    group: str  # csv | json | log
    description: str
    input_files: tuple[Path, ...]  # absolute paths on host, copied into workspace
    expected_path: Path
    accept: Callable[[Path], tuple[bool, str]]  # (passed, reason)
    output_filename: str = "output.csv"

    @property
    def directory(self) -> Path:
        return EVAL_TASKS_DIR / self.group / self.id


_REGISTRY: dict[str, Task] = {}


def register(task: Task) -> Task:
    if task.id in _REGISTRY:
        raise ValueError(f"Duplicate task id: {task.id}")
    _REGISTRY[task.id] = task
    return task


def all_tasks() -> list[Task]:
    _autodiscover()
    return sorted(_REGISTRY.values(), key=lambda t: t.id)


def get_task(task_id: str) -> Task:
    _autodiscover()
    if task_id not in _REGISTRY:
        raise KeyError(f"Unknown task: {task_id}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[task_id]


def tasks_in_group(group: str) -> list[Task]:
    return [t for t in all_tasks() if t.group == group]


_DISCOVERED = False


def _autodiscover() -> None:
    """Walk subpackages and import every `task.py` so registrations fire."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    pkg_root = Path(__file__).parent
    for group_dir in pkg_root.iterdir():
        if not group_dir.is_dir() or group_dir.name.startswith(("_", ".", "fixtures")):
            continue
        for task_dir in group_dir.iterdir():
            if not task_dir.is_dir():
                continue
            task_module = task_dir / "task.py"
            if not task_module.exists():
                continue
            mod_name = f"mercury.eval.tasks.{group_dir.name}.{task_dir.name}.task"
            importlib.import_module(mod_name)
    _DISCOVERED = True
