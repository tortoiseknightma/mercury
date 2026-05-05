"""Bench runner — execute one or many tasks, aggregate results.

Layered on top of `cli.run`'s machinery: extracted into a typer-free function
so `mercury bench` and `mercury report` can drive it programmatically without
the CLI's console output and `sys.exit` semantics.

Per-task work:
  - prepare a fresh workspace (input files copied in)
  - construct the manifest for the mode (`evolved` → verified skills only;
    `baseline` / `evolve` → empty)
  - spin up a DockerSandbox + compiled graph
  - invoke once with `recursion_limit=64`
  - persist the trace to JSONL and return a `TaskResult` dataclass

Per-bench work:
  - iterate tasks sequentially (Docker container startup contention + DashScope
    rate limits make parallelism brittle on hand-sized task sets)
  - aggregate `TaskResult`s into a `BenchResult`
  - persist to `results/metrics_<mode>.json` for later `mercury report`
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from mercury.config import RESULTS_DIR
from mercury.eval.tasks import Task, all_tasks, get_task
from mercury.graph import build_app
from mercury.sandbox import DockerSandbox
from mercury.skills.loader import manifest_to_dicts, scan_manifest
from mercury.state import new_trace
from mercury.trace import save_trace
from mercury.workspace import prepare


# ----------------------------------------------------------------- dataclasses


@dataclass
class TaskResult:
    task_id: str
    group: str
    mode: str
    success: bool
    tokens: int
    turns: int
    workspace: str
    trace_path: str
    synthesized_skill_path: Optional[str] = None
    verifier_verdict: Optional[str] = None
    rejection_reason: Optional[str] = None
    last_reason: Optional[str] = None  # acceptance reason from last submit


@dataclass
class BenchResult:
    mode: str
    timestamp: str
    tasks: list[TaskResult]


# ----------------------------------------------------------------- helpers


def _build_manifest_for_mode(mode: str) -> list[dict[str, str]]:
    """Only `evolved` mode loads verified skills; baseline / evolve see []."""
    if mode == "evolved":
        return manifest_to_dicts(scan_manifest(status="verified"))
    return []


# ----------------------------------------------------------------- single run


def run_one_task(
    task: Task,
    *,
    mode: str,
    run_idx: int = 0,
    db_path: Optional[Path] = None,
) -> TaskResult:
    """Run one task end-to-end. No console output; returns aggregated TaskResult."""
    workspace = prepare(task, run_label=f"{mode}_{run_idx}")
    manifest = _build_manifest_for_mode(mode)
    trace = new_trace(task.id, task.description, mode)  # type: ignore[arg-type]
    thread_id = f"{task.id}__{mode}__{run_idx}__{uuid.uuid4().hex[:6]}"

    with DockerSandbox(workspace) as sbx:
        graph_app, last_acceptance, conn = build_app(
            workspace=workspace,
            sandbox=sbx,
            accept_fn=task.accept,
            mode=mode,  # type: ignore[arg-type]
            task_group=task.group,
            db_path=db_path,
        )
        try:
            initial_state = {
                "task_id": task.id,
                "task": task.description,
                "workspace_dir": str(workspace),
                "messages": [],
                "scratchpad": {},
                "skill_manifest": manifest,
                "loaded_skill_bodies": {},
                "trace": trace,
                "consecutive_no_tool": 0,
                "done": False,
            }
            final_state = graph_app.invoke(
                initial_state,
                config={
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": 64,
                },
            )
        finally:
            conn.close()

    final_trace = final_state["trace"]
    trace_path = save_trace(final_trace, run_idx)

    verification = final_state.get("verification_outcome") or {}
    return TaskResult(
        task_id=task.id,
        group=task.group,
        mode=mode,
        success=bool(final_trace.get("success")),
        tokens=int(final_trace.get("total_tokens", 0)),
        turns=int(final_trace.get("total_turns", 0)),
        workspace=str(workspace),
        trace_path=str(trace_path),
        synthesized_skill_path=final_state.get("synthesized_skill_path"),
        verifier_verdict=verification.get("verdict"),
        rejection_reason=verification.get("rejection_reason"),
        last_reason=last_acceptance.get("reason") or None,
    )


# ----------------------------------------------------------------- bench


def run_bench(
    mode: str,
    *,
    task_ids: Optional[Iterable[str]] = None,
    progress_cb=None,
) -> BenchResult:
    """Run `task_ids` (or `all_tasks()`) sequentially in `mode`.

    `progress_cb(idx, total, task, result | None)` is invoked once before each
    task starts (with `result=None`) and once after it finishes. CLI uses it
    to drive a rich progress bar; tests can leave it None.
    """
    tasks = [get_task(tid) for tid in task_ids] if task_ids else all_tasks()
    results: list[TaskResult] = []
    total = len(tasks)
    for idx, task in enumerate(tasks):
        if progress_cb is not None:
            progress_cb(idx, total, task, None)
        result = run_one_task(task, mode=mode)
        results.append(result)
        if progress_cb is not None:
            progress_cb(idx, total, task, result)
    return BenchResult(
        mode=mode,
        timestamp=datetime.now(timezone.utc).isoformat(),
        tasks=results,
    )


# ----------------------------------------------------------------- persistence


def metrics_path(mode: str) -> Path:
    return RESULTS_DIR / f"metrics_{mode}.json"


def save_bench(result: BenchResult, *, path: Optional[Path] = None) -> Path:
    """Persist a BenchResult to `results/metrics_<mode>.json` (default)."""
    target = path or metrics_path(result.mode)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": result.mode,
        "timestamp": result.timestamp,
        "tasks": [asdict(t) for t in result.tasks],
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def load_bench(path: Path) -> BenchResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return BenchResult(
        mode=payload["mode"],
        timestamp=payload["timestamp"],
        tasks=[TaskResult(**t) for t in payload["tasks"]],
    )
