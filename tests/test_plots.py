"""Plot smoke tests — ensure files are produced, non-empty, valid PNG header."""

from __future__ import annotations

from pathlib import Path

import pytest

from mercury.eval.plots import (
    plot_pass_at_1_bars,
    plot_tokens_per_task,
    plot_tokens_radar,
    render_all,
)
from mercury.eval.runner import BenchResult, TaskResult


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _t(task_id: str, group: str, success: bool, tokens: int, turns: int, mode: str) -> TaskResult:
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


def _baseline_evolved() -> tuple[BenchResult, BenchResult]:
    baseline = _bench(
        "baseline",
        _t("csv-001", "csv", True, 5000, 3, "baseline"),
        _t("csv-002", "csv", True, 7000, 4, "baseline"),
        _t("csv-003", "csv", False, 9000, 5, "baseline"),
        _t("json-001", "json", True, 4500, 3, "baseline"),
    )
    evolved = _bench(
        "evolved",
        _t("csv-001", "csv", True, 4800, 3, "evolved"),
        _t("csv-002", "csv", True, 6500, 3, "evolved"),
        _t("csv-003", "csv", True, 7500, 4, "evolved"),
        _t("json-001", "json", True, 4500, 3, "evolved"),
    )
    return baseline, evolved


def _is_png(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0 and path.read_bytes()[:8] == PNG_MAGIC


def test_pass_at_1_bars_writes_png(tmp_path: Path) -> None:
    baseline, evolved = _baseline_evolved()
    out = plot_pass_at_1_bars(baseline, evolved, save_to=tmp_path / "p.png")
    assert _is_png(out)


def test_tokens_per_task_writes_png(tmp_path: Path) -> None:
    baseline, evolved = _baseline_evolved()
    out = plot_tokens_per_task(baseline, evolved, save_to=tmp_path / "t.png")
    assert _is_png(out)


def test_tokens_radar_writes_png(tmp_path: Path) -> None:
    baseline, evolved = _baseline_evolved()
    out = plot_tokens_radar(baseline, evolved, save_to=tmp_path / "r.png")
    assert _is_png(out)


def test_radar_falls_back_for_tiny_benches(tmp_path: Path) -> None:
    """Fewer than 3 tasks → radar gracefully degrades to a line plot."""
    baseline = _bench("baseline", _t("csv-001", "csv", True, 5000, 3, "baseline"))
    evolved = _bench("evolved", _t("csv-001", "csv", True, 4500, 3, "evolved"))
    out = plot_tokens_radar(baseline, evolved, save_to=tmp_path / "r.png")
    assert _is_png(out)


def test_pass_at_1_bars_handles_empty_groups(tmp_path: Path) -> None:
    baseline = _bench("baseline")
    evolved = _bench("evolved")
    out = plot_pass_at_1_bars(baseline, evolved, save_to=tmp_path / "p.png")
    assert _is_png(out)


def test_render_all_emits_three_files(tmp_path: Path) -> None:
    baseline, evolved = _baseline_evolved()
    paths = render_all(baseline, evolved, out_dir=tmp_path)
    assert len(paths) == 3
    for p in paths:
        assert _is_png(p)
    names = {p.name for p in paths}
    assert names == {"pass_at_1.png", "tokens_per_task.png", "tokens_radar.png"}
