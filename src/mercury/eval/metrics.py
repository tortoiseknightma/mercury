"""Aggregate metrics — Pass@1, average tokens / turns, normalized gain.

Pure functions: takes a `BenchResult`, returns a `BenchMetrics` dataclass.
No file I/O, no plotting, no LLM. Tested independently.

The headline number for `mercury report` is the **Normalized Gain**:

    g = (P_after - P_before) / (1 - P_before)

It rescales the raw Pass@1 delta against the available headroom — e.g. moving
from 0.6 → 0.8 (g=0.5) is a much bigger achievement than 0.0 → 0.2 (g=0.2),
even though the raw delta is identical. When the baseline is already at 1.0
we cap g at 0.0 (no headroom, no improvement to measure).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mercury.eval.runner import BenchResult, TaskResult


# ----------------------------------------------------------------- per-mode metrics


@dataclass
class GroupStats:
    n: int
    pass_at_1: float
    avg_tokens: float
    avg_turns: float


@dataclass
class BenchMetrics:
    mode: str
    n: int
    pass_at_1: float
    avg_tokens: float
    avg_turns: float
    by_group: dict[str, GroupStats] = field(default_factory=dict)


def _aggregate(tasks: list[TaskResult]) -> tuple[float, float, float]:
    """Returns (pass_at_1, avg_tokens, avg_turns). Empty list → all zero."""
    if not tasks:
        return 0.0, 0.0, 0.0
    n = len(tasks)
    return (
        sum(1 for t in tasks if t.success) / n,
        sum(t.tokens for t in tasks) / n,
        sum(t.turns for t in tasks) / n,
    )


def compute(result: BenchResult) -> BenchMetrics:
    """Aggregate a BenchResult into pass / tokens / turns + per-group breakdown."""
    pass_at_1, avg_tokens, avg_turns = _aggregate(result.tasks)

    by_group: dict[str, GroupStats] = {}
    for group in sorted({t.group for t in result.tasks}):
        ts = [t for t in result.tasks if t.group == group]
        gp, gt, gn = _aggregate(ts)
        by_group[group] = GroupStats(
            n=len(ts),
            pass_at_1=gp,
            avg_tokens=gt,
            avg_turns=gn,
        )

    return BenchMetrics(
        mode=result.mode,
        n=len(result.tasks),
        pass_at_1=pass_at_1,
        avg_tokens=avg_tokens,
        avg_turns=avg_turns,
        by_group=by_group,
    )


# ----------------------------------------------------------------- normalized gain


def normalized_gain(p_before: float, p_after: float) -> float:
    """Rescaled improvement against available headroom.

    g = (P_after - P_before) / (1 - P_before)

    Returns 0.0 when P_before == 1 (already at ceiling — no measurable gain).
    Negative values indicate regression.
    """
    if p_before >= 1.0:
        return 0.0
    return (p_after - p_before) / (1.0 - p_before)


# ----------------------------------------------------------------- comparison


@dataclass
class ComparisonMetrics:
    baseline: BenchMetrics
    evolved: BenchMetrics
    pass_delta: float
    normalized_gain: float
    tokens_ratio: Optional[float]   # evolved / baseline; <1 → improvement
    turns_ratio: Optional[float]


def compare(baseline: BenchResult, evolved: BenchResult) -> ComparisonMetrics:
    b = compute(baseline)
    e = compute(evolved)
    return ComparisonMetrics(
        baseline=b,
        evolved=e,
        pass_delta=e.pass_at_1 - b.pass_at_1,
        normalized_gain=normalized_gain(b.pass_at_1, e.pass_at_1),
        tokens_ratio=(e.avg_tokens / b.avg_tokens) if b.avg_tokens else None,
        turns_ratio=(e.avg_turns / b.avg_turns) if b.avg_turns else None,
    )
