"""Day 4 verifier — three-axis admission gate for synthesised skills.

A pending skill is promoted to `verified` only if all three checks hold:

  1. Source task — re-run the task that *produced* the skill, this time with
     the skill loaded into the manifest. Must `success ∧ tokens ≤ 0.85 ×
     baseline_tokens ∧ turns ≤ baseline_turns`. The recorded baseline lives in
     the skill's frontmatter (set by the synthesizer when the skill was first
     written, capturing the no-skill metrics that motivated it).

  2. Same-group neighbour — pick a different task from the same group and
     check it still succeeds with the skill loaded. We don't compare its
     tokens / turns because we don't cache neighbour baselines; we only need
     evidence that the skill doesn't break adjacent tasks.

  3. Cross-group anti-trigger — pick a task from a *different* group. The
     agent must NOT call `load_skill(<this skill>)` on it. If it does, the
     skill's `description` field is too broad and would invite spurious
     loading. (We don't require the cross-group task itself to succeed —
     loading is the only thing we care about here.)

Rejected skills are moved to `<library>/_rejected/<name>__<ts>/` together
with a `rejection.json` recording the metrics and the gate's reason. The
`scan_manifest` loader already skips `_`-prefixed dirs, so rejected skills
stay out of any future manifest.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from langgraph.graph import END, StateGraph

from mercury.config import SKILL_LIBRARY_DIR, load_config
from mercury.eval.tasks import Task, all_tasks
from mercury.llm import build_llm
from mercury.nodes.executor import make_executor_node
from mercury.sandbox import DockerSandbox
from mercury.skills.loader import load_full, parse_skill_file, write_skill_file
from mercury.state import AgentState, new_trace
from mercury.tools import build_tools
from mercury.workspace import prepare


TOKEN_BUDGET_RATIO = 0.85


# --------------------------------------------------------------- data


@dataclass
class RunMetrics:
    """One executor run under verification."""

    task_id: str
    success: bool
    tokens: int
    turns: int
    loaded_skill: bool  # did the agent call load_skill(<candidate>) ?


@dataclass
class VerificationOutcome:
    skill_name: str
    verdict: str  # "verified" | "rejected"
    rejection_reason: Optional[str]
    source: Optional[dict]
    neighbor: Optional[dict]
    anti_trigger: Optional[dict]
    timestamp: str


# --------------------------------------------------------------- pure logic


def gate_decision(
    *,
    source: Optional[RunMetrics],
    neighbor: Optional[RunMetrics],
    anti: Optional[RunMetrics],
    baseline_tokens: int,
    baseline_turns: int,
) -> tuple[str, Optional[str]]:
    """Pure verdict function. Tested independently of file I/O / LLM calls.

    Returns ("verified", None) or ("rejected", reason).
    """
    if source is None:
        return "rejected", "source task could not be run"
    if not source.success:
        return "rejected", f"source task '{source.task_id}' failed under skill"

    token_budget = max(1, int(baseline_tokens * TOKEN_BUDGET_RATIO))
    if source.tokens > token_budget:
        return (
            "rejected",
            f"tokens regression on source: {source.tokens} > 0.85 × baseline "
            f"({baseline_tokens}) = {token_budget}",
        )
    if source.turns > baseline_turns:
        return (
            "rejected",
            f"turns regression on source: {source.turns} > baseline ({baseline_turns})",
        )

    if neighbor is not None and not neighbor.success:
        return "rejected", f"neighbour task '{neighbor.task_id}' failed under skill"

    if anti is not None and anti.loaded_skill:
        return (
            "rejected",
            f"trigger description too broad: anti-trigger task '{anti.task_id}' "
            f"loaded the skill",
        )

    return "verified", None


def pick_verification_tasks(
    source_task_id: str,
    *,
    catalog: list[Task],
) -> tuple[Optional[Task], Optional[Task]]:
    """Pick (same-group neighbour, cross-group anti-trigger).

    Either may be None if the catalog doesn't have a candidate. We sort by id
    and take the first match so the choice is deterministic.
    """
    source = next((t for t in catalog if t.id == source_task_id), None)
    if source is None:
        return (None, None)
    neighbours = sorted(
        (t for t in catalog if t.group == source.group and t.id != source_task_id),
        key=lambda t: t.id,
    )
    cross = sorted(
        (t for t in catalog if t.group != source.group),
        key=lambda t: t.id,
    )
    return (neighbours[0] if neighbours else None, cross[0] if cross else None)


# --------------------------------------------------------------- file ops


def promote_skill(skill_dir: Path) -> None:
    """Flip `status: pending` → `verified` in place."""
    skill_md = skill_dir / "SKILL.md"
    fm, body = parse_skill_file(skill_md)
    fm = fm.model_copy(update={"status": "verified"})
    write_skill_file(skill_md, fm, body)


def archive_rejection(
    skill_dir: Path,
    *,
    outcome: VerificationOutcome,
    rejected_root: Path,
) -> Path:
    """Move the skill dir under `_rejected/<name>__<ts>/` and dump rejection.json."""
    rejected_root.mkdir(parents=True, exist_ok=True)
    safe_ts = outcome.timestamp.replace(":", "-").replace(".", "-")
    target = rejected_root / f"{outcome.skill_name}__{safe_ts}"
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(skill_dir), str(target))
    (target / "rejection.json").write_text(
        json.dumps(asdict(outcome), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target


# --------------------------------------------------------------- runner


RunnerFn = Callable[[Task, list[dict[str, str]], Optional[str]], RunMetrics]


def run_task_with_manifest(
    task: Task,
    manifest: list[dict[str, str]],
    target_skill: Optional[str] = None,
) -> RunMetrics:
    """Compile a one-shot executor graph and run `task` with a custom manifest.

    No checkpointer — verification runs are throwaway. The DockerSandbox is
    spun up per-call (one container per verification probe); that's the same
    cost model as a normal `mercury run`.

    Records `loaded_skill=True` if the agent called `load_skill(<target>)`
    during the run. Used for the anti-trigger check.
    """
    cfg = load_config()
    workspace = prepare(task, run_label=f"verify_{uuid.uuid4().hex[:6]}")

    last_acceptance: dict = {"passed": False, "reason": "", "output_path": ""}

    def on_submit(output_path: str, _note: str) -> dict:
        passed, reason = task.accept(workspace)
        last_acceptance["passed"] = passed
        last_acceptance["reason"] = reason
        last_acceptance["output_path"] = output_path
        return {"passed": passed, "reason": reason, "output_path": output_path}

    # Probe must use the same model as the executor: baseline_metrics were
    # measured under that model, so a different model here would make the
    # 0.85× token budget meaningless.
    llm = build_llm("executor")

    with DockerSandbox(workspace) as sbx:
        tools = build_tools(
            workspace=workspace,
            sandbox=sbx,
            skill_loader=load_full,
            on_submit=on_submit,
        )
        executor_node = make_executor_node(
            llm=llm,
            tools=tools,
            max_steps=cfg.harness.max_steps,
        )
        graph = StateGraph(AgentState)
        graph.add_node("executor", executor_node)
        graph.set_entry_point("executor")
        graph.add_conditional_edges(
            "executor",
            lambda s: END if s.get("done") else "executor",
            {END: END, "executor": "executor"},
        )
        app = graph.compile()

        trace = new_trace(task.id, task.description, "verify")
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
        final_state = app.invoke(initial_state, config={"recursion_limit": 64})

    final_trace = final_state["trace"]
    loaded = False
    if target_skill is not None:
        for step in final_trace.get("steps", []):
            if step.get("tool") == "load_skill":
                args = step.get("args") or {}
                if args.get("name") == target_skill:
                    loaded = True
                    break
    return RunMetrics(
        task_id=task.id,
        success=bool(final_trace.get("success")),
        tokens=int(final_trace.get("total_tokens", 0)),
        turns=int(final_trace.get("total_turns", 0)),
        loaded_skill=loaded,
    )


# --------------------------------------------------------------- orchestration


def verify_skill(
    skill_name: str,
    *,
    library_dir: Optional[Path] = None,
    runner: Optional[RunnerFn] = None,
    catalog: Optional[list[Task]] = None,
) -> VerificationOutcome:
    """Verify a pending skill. Promote on success, archive on rejection.

    Args:
        skill_name: kebab-case directory name in the library.
        library_dir: override (tests). Defaults to SKILL_LIBRARY_DIR.
        runner: stub-able executor runner. Defaults to run_task_with_manifest.
        catalog: stub-able task catalog. Defaults to all_tasks().
    """
    base = library_dir or SKILL_LIBRARY_DIR
    rejected_root = base / "_rejected"
    skill_dir = base / skill_name
    skill_md = skill_dir / "SKILL.md"

    timestamp = datetime.now(timezone.utc).isoformat()
    if not skill_md.exists():
        return VerificationOutcome(
            skill_name=skill_name,
            verdict="rejected",
            rejection_reason="SKILL.md not found",
            source=None,
            neighbor=None,
            anti_trigger=None,
            timestamp=timestamp,
        )

    fm, _ = parse_skill_file(skill_md)
    if fm.baseline_metrics is None or fm.source_task is None:
        outcome = VerificationOutcome(
            skill_name=skill_name,
            verdict="rejected",
            rejection_reason="missing baseline_metrics or source_task in frontmatter",
            source=None,
            neighbor=None,
            anti_trigger=None,
            timestamp=timestamp,
        )
        archive_rejection(skill_dir, outcome=outcome, rejected_root=rejected_root)
        return outcome

    catalog = catalog if catalog is not None else all_tasks()
    runner = runner or run_task_with_manifest
    manifest = [{"name": fm.name, "description": fm.description}]

    source_task = next((t for t in catalog if t.id == fm.source_task), None)
    if source_task is None:
        outcome = VerificationOutcome(
            skill_name=skill_name,
            verdict="rejected",
            rejection_reason=f"source_task '{fm.source_task}' not in catalog",
            source=None,
            neighbor=None,
            anti_trigger=None,
            timestamp=timestamp,
        )
        archive_rejection(skill_dir, outcome=outcome, rejected_root=rejected_root)
        return outcome

    source_metrics = runner(source_task, manifest, fm.name)

    neighbour, anti = pick_verification_tasks(fm.source_task, catalog=catalog)
    neighbour_metrics = runner(neighbour, manifest, fm.name) if neighbour else None
    anti_metrics = runner(anti, manifest, fm.name) if anti else None

    verdict, reason = gate_decision(
        source=source_metrics,
        neighbor=neighbour_metrics,
        anti=anti_metrics,
        baseline_tokens=fm.baseline_metrics.tokens,
        baseline_turns=fm.baseline_metrics.turns,
    )

    outcome = VerificationOutcome(
        skill_name=skill_name,
        verdict=verdict,
        rejection_reason=reason,
        source=asdict(source_metrics),
        neighbor=asdict(neighbour_metrics) if neighbour_metrics else None,
        anti_trigger=asdict(anti_metrics) if anti_metrics else None,
        timestamp=timestamp,
    )

    if verdict == "verified":
        promote_skill(skill_dir)
    else:
        archive_rejection(skill_dir, outcome=outcome, rejected_root=rejected_root)
    return outcome


# --------------------------------------------------------------- graph node


def make_verifier_node():
    def verifier_node(state: AgentState) -> dict:
        skill_path_str = state.get("synthesized_skill_path")
        if not skill_path_str:
            return {"verification_outcome": None}
        skill_dir = Path(skill_path_str).parent
        outcome = verify_skill(skill_dir.name)
        return {"verification_outcome": asdict(outcome)}

    return verifier_node
