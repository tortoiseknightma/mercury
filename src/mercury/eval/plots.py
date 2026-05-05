"""Plot baseline-vs-evolved benches.

Three figures land in `results/plots/`:

  - `pass_at_1.png`     — per-group Pass@1 grouped bars
  - `tokens_per_task.png` — per-task tokens, baseline vs evolved
  - `tokens_radar.png`  — per-task tokens on a polar radar (smaller polygon = better)

We use matplotlib's `Agg` backend so there's no display server required and
the same code path works in CI / on a headless box. Figures are closed after
saving to keep memory bounded if `mercury report` is invoked many times.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mercury.config import PLOTS_DIR
from mercury.eval.metrics import compute
from mercury.eval.runner import BenchResult, TaskResult


# --------------------------------------------------------------- helpers


def _aligned_task_ids(*benches: BenchResult) -> list[str]:
    """Sorted union of task ids across all benches."""
    ids: set[str] = set()
    for b in benches:
        for t in b.tasks:
            ids.add(t.task_id)
    return sorted(ids)


def _index_by_id(bench: BenchResult) -> dict[str, TaskResult]:
    return {t.task_id: t for t in bench.tasks}


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------- figure 1: bars


def plot_pass_at_1_bars(
    baseline: BenchResult,
    evolved: BenchResult,
    *,
    save_to: Path,
) -> Path:
    """Per-group Pass@1, grouped bars."""
    b = compute(baseline)
    e = compute(evolved)
    groups = sorted(set(b.by_group) | set(e.by_group))
    if not groups:
        groups = ["all"]
        b_vals = [b.pass_at_1]
        e_vals = [e.pass_at_1]
    else:
        b_vals = [b.by_group[g].pass_at_1 if g in b.by_group else 0.0 for g in groups]
        e_vals = [e.by_group[g].pass_at_1 if g in e.by_group else 0.0 for g in groups]

    x = np.arange(len(groups))
    width = 0.38

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width / 2, b_vals, width, label="baseline", color="#1f77b4")
    ax.bar(x + width / 2, e_vals, width, label="evolved", color="#2ca02c")
    ax.set_xticks(x)
    ax.set_xticklabels(groups)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Pass@1")
    ax.set_title(f"Pass@1 by group  (overall: {b.pass_at_1:.2f} → {e.pass_at_1:.2f})")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    _ensure_dir(save_to)
    fig.tight_layout()
    fig.savefig(save_to, dpi=120)
    plt.close(fig)
    return save_to


# --------------------------------------------------------------- figure 2: tokens line


def plot_tokens_per_task(
    baseline: BenchResult,
    evolved: BenchResult,
    *,
    save_to: Path,
) -> Path:
    """Per-task tokens, baseline vs evolved (line plot, sorted by task id)."""
    ids = _aligned_task_ids(baseline, evolved)
    bi = _index_by_id(baseline)
    ei = _index_by_id(evolved)
    b_tokens = [bi[t].tokens if t in bi else np.nan for t in ids]
    e_tokens = [ei[t].tokens if t in ei else np.nan for t in ids]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(ids, b_tokens, marker="o", color="#1f77b4", label="baseline")
    ax.plot(ids, e_tokens, marker="s", color="#2ca02c", label="evolved")
    ax.set_ylabel("tokens")
    ax.set_title("Tokens per task")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    _ensure_dir(save_to)
    fig.tight_layout()
    fig.savefig(save_to, dpi=120)
    plt.close(fig)
    return save_to


# --------------------------------------------------------------- figure 3: radar


def plot_tokens_radar(
    baseline: BenchResult,
    evolved: BenchResult,
    *,
    save_to: Path,
) -> Path:
    """Per-task tokens as a polar radar.

    Smaller polygon = lower tokens = better. Both polygons are closed so a
    visual sweep tells you whether evolved generally inscribes baseline.
    """
    ids = _aligned_task_ids(baseline, evolved)
    if len(ids) < 3:
        # A radar needs ≥ 3 axes to be meaningful — fall back to a degenerate
        # chart so callers don't have to special-case tiny benches.
        return plot_tokens_per_task(baseline, evolved, save_to=save_to)

    bi = _index_by_id(baseline)
    ei = _index_by_id(evolved)
    b_tokens = [bi[t].tokens if t in bi else 0 for t in ids]
    e_tokens = [ei[t].tokens if t in ei else 0 for t in ids]

    angles = np.linspace(0, 2 * np.pi, len(ids), endpoint=False).tolist()
    angles += angles[:1]
    b_closed = b_tokens + b_tokens[:1]
    e_closed = e_tokens + e_tokens[:1]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw={"projection": "polar"})
    ax.plot(angles, b_closed, color="#1f77b4", linewidth=2, label="baseline")
    ax.fill(angles, b_closed, color="#1f77b4", alpha=0.18)
    ax.plot(angles, e_closed, color="#2ca02c", linewidth=2, label="evolved")
    ax.fill(angles, e_closed, color="#2ca02c", alpha=0.18)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(ids, fontsize=9)
    ax.set_title("Tokens per task (radar — smaller polygon = better)", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.2, 1.05))

    _ensure_dir(save_to)
    fig.tight_layout()
    fig.savefig(save_to, dpi=120)
    plt.close(fig)
    return save_to


# --------------------------------------------------------------- pipeline


def render_all(
    baseline: BenchResult,
    evolved: BenchResult,
    *,
    out_dir: Path | None = None,
) -> list[Path]:
    """Render the three standard plots into `out_dir` (default: PLOTS_DIR)."""
    out_dir = out_dir or PLOTS_DIR
    return [
        plot_pass_at_1_bars(baseline, evolved, save_to=out_dir / "pass_at_1.png"),
        plot_tokens_per_task(baseline, evolved, save_to=out_dir / "tokens_per_task.png"),
        plot_tokens_radar(baseline, evolved, save_to=out_dir / "tokens_radar.png"),
    ]
