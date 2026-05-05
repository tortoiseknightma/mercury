"""TraceCard persistence — JSONL on disk, one file per task per run."""

from __future__ import annotations

import json
from pathlib import Path

from mercury.config import TRACES_DIR
from mercury.state import TraceCard


def trace_path(task_id: str, mode: str, run_idx: int = 0) -> Path:
    return TRACES_DIR / f"{task_id}__{mode}__{run_idx:02d}.jsonl"


def save_trace(trace: TraceCard, run_idx: int = 0) -> Path:
    """Append-style: one JSON line per step + one final summary line.

    JSONL form makes it easy to tail and inspect with `cat results/traces/...`.
    """
    p = trace_path(trace["task_id"], trace["mode"], run_idx)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        # Header: trace metadata sans steps.
        header = {k: v for k, v in trace.items() if k != "steps"}
        header["_kind"] = "header"
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        for step in trace["steps"]:
            line = dict(step)
            line["_kind"] = "step"
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return p


def load_trace(path: Path) -> TraceCard:
    header: dict = {}
    steps: list = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            kind = obj.pop("_kind", None)
            if kind == "header":
                header = obj
            elif kind == "step":
                steps.append(obj)
    header["steps"] = steps
    return header  # type: ignore[return-value]
