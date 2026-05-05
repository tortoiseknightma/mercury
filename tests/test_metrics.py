"""Pure metrics — Pass@1 / averages / Normalized Gain / per-group split."""

from __future__ import annotations

import pytest

from mercury.eval.metrics import (
    BenchMetrics,
    ComparisonMetrics,
    compare,
    compute,
    normalized_gain,
)
from mercury.eval.runner import BenchResult, TaskResult


def _t(task_id: str, group: str, success: bool, tokens: int, turns: int, mode: str = "baseline") -> TaskResult:
    return TaskResult(
        task_id=task_id,
        group=group,
        mode=mode,
        success=success,
        tokens=tokens,
        turns=turns,
        workspace="/tmp/x",
        trace_path="/tmp/x.jsonl",
    )


def _bench(mode: str, *tasks: TaskResult) -> BenchResult:
    return BenchResult(mode=mode, timestamp="2026-05-03T00:00:00+00:00", tasks=list(tasks))


# ---------------------------------------------------------------- compute


def test_compute_handles_empty_bench() -> None:
    m = compute(_bench("baseline"))
    assert m.n == 0
    assert m.pass_at_1 == 0.0
    assert m.avg_tokens == 0.0
    assert m.avg_turns == 0.0
    assert m.by_group == {}


def test_compute_pass_at_1_and_averages() -> None:
    bench = _bench(
        "baseline",
        _t("csv-001", "csv", True, 4000, 3),
        _t("csv-002", "csv", True, 6000, 4),
        _t("csv-003", "csv", False, 8000, 5),
        _t("json-001", "json", True, 5000, 3),
    )
    m = compute(bench)
    assert m.n == 4
    assert m.pass_at_1 == pytest.approx(0.75)
    assert m.avg_tokens == pytest.approx(5750)
    assert m.avg_turns == pytest.approx(3.75)


def test_compute_breaks_down_by_group() -> None:
    bench = _bench(
        "evolved",
        _t("csv-001", "csv", True, 4000, 3),
        _t("csv-002", "csv", False, 8000, 5),
        _t("json-001", "json", True, 5000, 3),
    )
    m = compute(bench)
    assert set(m.by_group) == {"csv", "json"}
    assert m.by_group["csv"].n == 2
    assert m.by_group["csv"].pass_at_1 == pytest.approx(0.5)
    assert m.by_group["csv"].avg_tokens == pytest.approx(6000)
    assert m.by_group["json"].n == 1
    assert m.by_group["json"].pass_at_1 == pytest.approx(1.0)


# ---------------------------------------------------------------- normalized gain


def test_normalized_gain_textbook_case() -> None:
    # 0.6 → 0.8 against headroom 0.4 is g=0.5
    assert normalized_gain(0.6, 0.8) == pytest.approx(0.5)


def test_normalized_gain_zero_baseline() -> None:
    # When P_before=0 the formula reduces to g = P_after.
    assert normalized_gain(0.0, 0.4) == pytest.approx(0.4)


def test_normalized_gain_caps_at_zero_when_baseline_perfect() -> None:
    """If baseline is already 1.0 there is no headroom to gain."""
    assert normalized_gain(1.0, 1.0) == 0.0
    assert normalized_gain(1.0, 0.5) == 0.0  # arithmetic would explode; clamp


def test_normalized_gain_negative_on_regression() -> None:
    # 0.6 → 0.4 against headroom 0.4 is g=-0.5
    assert normalized_gain(0.6, 0.4) == pytest.approx(-0.5)


# ---------------------------------------------------------------- compare


def test_compare_propagates_deltas_and_ratios() -> None:
    baseline = _bench(
        "baseline",
        _t("csv-001", "csv", True, 5000, 4),
        _t("csv-002", "csv", False, 10000, 8),
    )
    evolved = _bench(
        "evolved",
        _t("csv-001", "csv", True, 4000, 3),
        _t("csv-002", "csv", True, 7000, 5),
    )
    cmp_ = compare(baseline, evolved)
    assert cmp_.baseline.pass_at_1 == pytest.approx(0.5)
    assert cmp_.evolved.pass_at_1 == pytest.approx(1.0)
    assert cmp_.pass_delta == pytest.approx(0.5)
    # 0.5 → 1.0 with headroom 0.5 → g = 1.0 (full lift)
    assert cmp_.normalized_gain == pytest.approx(1.0)
    # tokens ratio: avg evolved 5500 vs baseline 7500 → 0.733
    assert cmp_.tokens_ratio == pytest.approx(5500 / 7500)
    # turns ratio: avg evolved 4 vs baseline 6 → 0.667
    assert cmp_.turns_ratio == pytest.approx(4.0 / 6.0)


def test_compare_handles_zero_baseline_avg_tokens() -> None:
    """Empty baseline → tokens_ratio is None instead of ZeroDivisionError."""
    baseline = _bench("baseline")  # no tasks
    evolved = _bench("evolved", _t("csv-001", "csv", True, 4000, 3))
    cmp_ = compare(baseline, evolved)
    assert cmp_.tokens_ratio is None
    assert cmp_.turns_ratio is None
