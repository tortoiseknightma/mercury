"""Synthesizer node — turn the evaluator's proposal into a SKILL.md file.

Pure I/O. No LLM calls. The skill is written with `status: pending`, and
records a `baseline_metrics` snapshot of the run that motivated it so the
verifier (Day 4) can decide whether the skill actually beats baseline.
"""

from __future__ import annotations

import re
from pathlib import Path

from mercury.config import SKILL_LIBRARY_DIR
from mercury.skills.loader import write_skill_file
from mercury.skills.schema import BaselineMetrics, SkillFrontmatter
from mercury.state import AgentState


_KEBAB_OK = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _sanitise_name(raw: str) -> str:
    """Coerce arbitrary skill names into safe directory names."""
    s = raw.strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:64] or "skill"


def synthesize_skill(
    *,
    proposed: dict,
    task_id: str,
    task_group: str | None,
    baseline_tokens: int,
    baseline_turns: int,
    library_dir: Path | None = None,
) -> Path | None:
    """Pure helper used by both the graph node and tests.

    Returns the written SKILL.md path, or None if `should_synthesize` was
    false / required fields were missing.
    """
    if not proposed.get("should_synthesize"):
        return None
    name = proposed.get("skill_name") or ""
    desc = proposed.get("trigger_description") or ""
    body = proposed.get("instructions_md") or ""
    if not (name and desc and body):
        return None

    name = _sanitise_name(name)
    if not _KEBAB_OK.match(name):
        return None

    base = library_dir or SKILL_LIBRARY_DIR
    skill_dir = base / name
    if (skill_dir / "SKILL.md").exists():
        # Idempotent: never overwrite an existing skill.
        return None

    applies_to = [task_group] if task_group else []
    fm = SkillFrontmatter(
        name=name,
        description=desc,
        version=1,
        applies_to=applies_to,
        status="pending",
        source_task=task_id,
        baseline_metrics=BaselineMetrics(tokens=baseline_tokens, turns=baseline_turns),
    )
    skill_md_path = skill_dir / "SKILL.md"
    write_skill_file(skill_md_path, fm, body)
    return skill_md_path


def make_synthesizer_node(*, task_group: str | None = None):
    def synthesizer_node(state: AgentState) -> dict:
        proposed = state.get("proposed_skill") or {}
        trace = state.get("trace") or {}
        path = synthesize_skill(
            proposed=proposed,
            task_id=state.get("task_id", "unknown"),
            task_group=task_group,
            baseline_tokens=trace.get("total_tokens", 0),
            baseline_turns=trace.get("total_turns", 0),
        )
        # Record the file we wrote (or None) so verifier / tests can pick it up.
        return {"synthesized_skill_path": str(path) if path else None}

    return synthesizer_node
