"""Verifier — three-axis gate logic, frontmatter promotion, rejection archive,
and end-to-end orchestration with a stubbed executor runner.

These tests deliberately don't touch Docker or the real LLM; the runner is
injected so we can drive every gate branch deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mercury.eval.tasks import Task
from mercury.nodes.verifier import (
    RunMetrics,
    TOKEN_BUDGET_RATIO,
    VerificationOutcome,
    archive_rejection,
    gate_decision,
    pick_verification_tasks,
    promote_skill,
    verify_skill,
)
from mercury.skills.loader import parse_skill_file, write_skill_file
from mercury.skills.schema import BaselineMetrics, SkillFrontmatter


# ----------------------------------------------------------- helpers


def _stub_task(id_: str, group: str) -> Task:
    return Task(
        id=id_,
        group=group,
        description="x",
        input_files=(),
        expected_path=Path("x"),
        accept=lambda _w: (True, "ok"),
    )


def _make_pending(
    library: Path,
    name: str,
    *,
    source_task: str = "csv-002",
    baseline_tokens: int = 7000,
    baseline_turns: int = 4,
    description: str = "When the CSV has dirty whitespace, use this skill.",
) -> Path:
    fm = SkillFrontmatter(
        name=name,
        description=description,
        applies_to=["csv"],
        status="pending",
        source_task=source_task,
        baseline_metrics=BaselineMetrics(tokens=baseline_tokens, turns=baseline_turns),
    )
    skill_md = library / name / "SKILL.md"
    write_skill_file(skill_md, fm, "## When to use\nfoo\n\n## Steps\n1. bar\n")
    return skill_md


# ----------------------------------------------------------- gate_decision (pure)


def test_gate_passes_when_all_axes_within_budget() -> None:
    source = RunMetrics("csv-002", success=True, tokens=5000, turns=3, loaded_skill=True)
    nb = RunMetrics("csv-001", success=True, tokens=4000, turns=3, loaded_skill=True)
    anti = RunMetrics("json-001", success=True, tokens=4000, turns=3, loaded_skill=False)
    verdict, reason = gate_decision(
        source=source,
        neighbor=nb,
        anti=anti,
        baseline_tokens=7000,
        baseline_turns=4,
    )
    assert verdict == "verified"
    assert reason is None


def test_gate_rejects_on_token_regression() -> None:
    # 0.85 * 7000 = 5950; 6000 just exceeds budget.
    source = RunMetrics("csv-002", success=True, tokens=6000, turns=3, loaded_skill=True)
    verdict, reason = gate_decision(
        source=source, neighbor=None, anti=None, baseline_tokens=7000, baseline_turns=4
    )
    assert verdict == "rejected"
    assert "tokens regression" in reason


def test_gate_rejects_on_turns_regression() -> None:
    source = RunMetrics("csv-002", success=True, tokens=4000, turns=5, loaded_skill=True)
    verdict, reason = gate_decision(
        source=source, neighbor=None, anti=None, baseline_tokens=7000, baseline_turns=4
    )
    assert verdict == "rejected"
    assert "turns regression" in reason


def test_gate_rejects_on_source_failure() -> None:
    source = RunMetrics("csv-002", success=False, tokens=4000, turns=3, loaded_skill=True)
    verdict, reason = gate_decision(
        source=source, neighbor=None, anti=None, baseline_tokens=7000, baseline_turns=4
    )
    assert verdict == "rejected"
    assert "failed under skill" in reason


def test_gate_rejects_on_neighbour_failure() -> None:
    source = RunMetrics("csv-002", success=True, tokens=4000, turns=3, loaded_skill=True)
    nb = RunMetrics("csv-001", success=False, tokens=4000, turns=3, loaded_skill=True)
    verdict, reason = gate_decision(
        source=source, neighbor=nb, anti=None, baseline_tokens=7000, baseline_turns=4
    )
    assert verdict == "rejected"
    assert "neighbour" in reason


def test_gate_rejects_when_anti_trigger_loads_skill() -> None:
    source = RunMetrics("csv-002", success=True, tokens=4000, turns=3, loaded_skill=True)
    nb = RunMetrics("csv-001", success=True, tokens=4000, turns=3, loaded_skill=True)
    # The cross-group task mistakenly invoked load_skill — trigger too broad.
    anti = RunMetrics("json-001", success=True, tokens=4000, turns=3, loaded_skill=True)
    verdict, reason = gate_decision(
        source=source, neighbor=nb, anti=anti, baseline_tokens=7000, baseline_turns=4
    )
    assert verdict == "rejected"
    assert "too broad" in reason


def test_gate_rejects_when_source_metrics_missing() -> None:
    verdict, reason = gate_decision(
        source=None, neighbor=None, anti=None, baseline_tokens=7000, baseline_turns=4
    )
    assert verdict == "rejected"
    assert "could not be run" in reason


def test_token_budget_ratio_constant_pinned() -> None:
    """Hard-pin the gate ratio. Changing this requires a roadmap update."""
    assert TOKEN_BUDGET_RATIO == 0.85


# ----------------------------------------------------------- pick_verification_tasks


def test_pick_picks_smallest_neighbour_and_smallest_cross() -> None:
    catalog = [
        _stub_task("csv-003", "csv"),
        _stub_task("csv-001", "csv"),
        _stub_task("csv-002", "csv"),
        _stub_task("json-002", "json"),
        _stub_task("json-001", "json"),
    ]
    nb, anti = pick_verification_tasks("csv-002", catalog=catalog)
    assert nb is not None and nb.id == "csv-001"
    assert anti is not None and anti.id == "json-001"


def test_pick_returns_none_when_no_neighbour() -> None:
    catalog = [_stub_task("csv-001", "csv"), _stub_task("json-001", "json")]
    nb, anti = pick_verification_tasks("csv-001", catalog=catalog)
    assert nb is None
    assert anti is not None and anti.id == "json-001"


def test_pick_returns_none_when_no_cross_group() -> None:
    catalog = [_stub_task("csv-001", "csv"), _stub_task("csv-002", "csv")]
    nb, anti = pick_verification_tasks("csv-001", catalog=catalog)
    assert nb is not None and nb.id == "csv-002"
    assert anti is None


def test_pick_returns_none_when_source_unknown() -> None:
    catalog = [_stub_task("csv-001", "csv")]
    nb, anti = pick_verification_tasks("does-not-exist", catalog=catalog)
    assert nb is None and anti is None


# ----------------------------------------------------------- file ops


def test_promote_flips_status_in_place(tmp_path: Path) -> None:
    _make_pending(tmp_path, "x")
    promote_skill(tmp_path / "x")
    fm, body = parse_skill_file(tmp_path / "x" / "SKILL.md")
    assert fm.status == "verified"
    assert "## When to use" in body
    # The recorded baseline_metrics survives.
    assert fm.baseline_metrics is not None and fm.baseline_metrics.tokens == 7000


def test_archive_rejection_moves_skill_and_writes_json(tmp_path: Path) -> None:
    _make_pending(tmp_path, "x")
    rejected_root = tmp_path / "_rejected"
    outcome = VerificationOutcome(
        skill_name="x",
        verdict="rejected",
        rejection_reason="bad",
        source={"task_id": "csv-002", "success": False, "tokens": 0, "turns": 0, "loaded_skill": False},
        neighbor=None,
        anti_trigger=None,
        timestamp="2026-05-03T10:00:00+00:00",
    )
    target = archive_rejection(tmp_path / "x", outcome=outcome, rejected_root=rejected_root)
    assert not (tmp_path / "x").exists()
    assert (target / "SKILL.md").exists()
    rj = json.loads((target / "rejection.json").read_text(encoding="utf-8"))
    assert rj["skill_name"] == "x"
    assert rj["rejection_reason"] == "bad"
    # Timestamp colons must be filesystem-safe.
    assert ":" not in target.name


# ----------------------------------------------------------- verify_skill orchestration


def _full_catalog() -> list[Task]:
    return [
        _stub_task("csv-001", "csv"),
        _stub_task("csv-002", "csv"),
        _stub_task("csv-003", "csv"),
        _stub_task("json-001", "json"),
    ]


def test_verify_skill_promotes_when_runner_metrics_pass(tmp_path: Path) -> None:
    _make_pending(tmp_path, "x", baseline_tokens=10000, baseline_turns=5)

    def runner(task, _manifest, _target):
        return RunMetrics(
            task_id=task.id,
            success=True,
            tokens=5000,
            turns=3,
            loaded_skill=task.group == "csv",  # loads on csv (good), not on json
        )

    outcome = verify_skill("x", library_dir=tmp_path, runner=runner, catalog=_full_catalog())
    assert outcome.verdict == "verified"
    fm, _ = parse_skill_file(tmp_path / "x" / "SKILL.md")
    assert fm.status == "verified"
    # Anti-trigger metrics recorded but didn't trip the gate.
    assert outcome.anti_trigger is not None
    assert outcome.anti_trigger["task_id"] == "json-001"
    assert outcome.anti_trigger["loaded_skill"] is False


def test_verify_skill_rejects_too_broad_trigger(tmp_path: Path) -> None:
    """Anti-trigger task loads the skill → trigger description too broad."""
    _make_pending(tmp_path, "x", baseline_tokens=10000, baseline_turns=5)

    def runner(_task, _manifest, _target):
        return RunMetrics(
            task_id=_task.id,
            success=True,
            tokens=3000,
            turns=3,
            loaded_skill=True,  # ALWAYS loads, including anti-trigger
        )

    outcome = verify_skill("x", library_dir=tmp_path, runner=runner, catalog=_full_catalog())
    assert outcome.verdict == "rejected"
    assert "too broad" in outcome.rejection_reason
    assert not (tmp_path / "x").exists()
    # Archived under _rejected/ with rejection.json.
    rejected_dirs = list((tmp_path / "_rejected").iterdir())
    assert len(rejected_dirs) == 1
    rj = json.loads((rejected_dirs[0] / "rejection.json").read_text(encoding="utf-8"))
    assert rj["verdict"] == "rejected"
    assert rj["anti_trigger"]["loaded_skill"] is True


def test_verify_skill_rejects_token_regression(tmp_path: Path) -> None:
    """Source task burns more than 0.85 × baseline tokens — reject."""
    _make_pending(tmp_path, "x", baseline_tokens=1000, baseline_turns=5)  # tight budget

    def runner(task, _manifest, _target):
        return RunMetrics(
            task_id=task.id, success=True, tokens=2000, turns=3, loaded_skill=True
        )

    outcome = verify_skill("x", library_dir=tmp_path, runner=runner, catalog=_full_catalog())
    assert outcome.verdict == "rejected"
    assert "tokens regression" in outcome.rejection_reason
    rejected_dirs = list((tmp_path / "_rejected").iterdir())
    assert len(rejected_dirs) == 1


def test_verify_skill_rejects_when_source_fails(tmp_path: Path) -> None:
    _make_pending(tmp_path, "x", baseline_tokens=10000, baseline_turns=5)

    def runner(task, _manifest, _target):
        # Source task fails under the skill.
        return RunMetrics(
            task_id=task.id,
            success=task.id != "csv-002",
            tokens=3000,
            turns=3,
            loaded_skill=True,
        )

    outcome = verify_skill("x", library_dir=tmp_path, runner=runner, catalog=_full_catalog())
    assert outcome.verdict == "rejected"
    assert "csv-002" in outcome.rejection_reason


def test_verify_skill_skips_runner_when_baseline_metrics_missing(tmp_path: Path) -> None:
    """No baseline_metrics → reject upfront, never spend LLM tokens."""
    fm = SkillFrontmatter(
        name="y",
        description="trigger",
        status="pending",
        source_task="csv-002",
        # baseline_metrics omitted on purpose
    )
    write_skill_file(tmp_path / "y" / "SKILL.md", fm, "## When to use\nfoo")

    runner_calls: list[str] = []

    def runner(task, _manifest, _target):
        runner_calls.append(task.id)
        return RunMetrics(task.id, True, 0, 0, False)

    outcome = verify_skill("y", library_dir=tmp_path, runner=runner, catalog=_full_catalog())
    assert outcome.verdict == "rejected"
    assert "missing baseline_metrics" in outcome.rejection_reason
    assert runner_calls == [], "runner must not be called when frontmatter is invalid"


def test_verify_skill_handles_unknown_source_task(tmp_path: Path) -> None:
    """Skill points at a task that no longer exists — archive without LLM calls."""
    _make_pending(tmp_path, "z", source_task="csv-deleted-001")
    runner_calls: list[str] = []

    def runner(task, _manifest, _target):
        runner_calls.append(task.id)
        return RunMetrics(task.id, True, 0, 0, False)

    outcome = verify_skill("z", library_dir=tmp_path, runner=runner, catalog=_full_catalog())
    assert outcome.verdict == "rejected"
    assert "csv-deleted-001" in outcome.rejection_reason
    assert runner_calls == []
    assert not (tmp_path / "z").exists()


def test_verify_skill_handles_missing_skill_md(tmp_path: Path) -> None:
    outcome = verify_skill(
        "ghost", library_dir=tmp_path, runner=lambda *_: RunMetrics("x", True, 0, 0, False), catalog=[]
    )
    assert outcome.verdict == "rejected"
    assert "not found" in outcome.rejection_reason


def test_verify_skill_passes_when_no_neighbour_or_cross_in_catalog(tmp_path: Path) -> None:
    """Tiny catalog with only the source task — verifier still works."""
    _make_pending(tmp_path, "x", baseline_tokens=10000, baseline_turns=5)
    catalog = [_stub_task("csv-002", "csv")]

    def runner(task, _manifest, _target):
        return RunMetrics(task.id, True, 5000, 3, True)

    outcome = verify_skill("x", library_dir=tmp_path, runner=runner, catalog=catalog)
    assert outcome.verdict == "verified"
    assert outcome.neighbor is None
    assert outcome.anti_trigger is None
