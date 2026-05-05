"""Pydantic models for Anthropic-spec Agent Skill files."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


SkillStatus = Literal["pending", "verified", "rejected"]


class BaselineMetrics(BaseModel):
    """Snapshot of the run that *produced* the skill.

    Used by the verifier (Day 4) to gate admission: a verified skill must
    bring tokens / turns below the baseline that motivated it.
    """

    tokens: int = 0
    turns: int = 0


class SkillFrontmatter(BaseModel):
    """The YAML block at the top of a SKILL.md file."""

    name: str = Field(description="kebab-case identifier; matches the skill directory name.")
    description: str = Field(
        description=(
            "One-sentence trigger condition shown in the manifest. "
            "Future agents see this and decide whether to call `load_skill(name)`."
        )
    )
    version: int = 1
    applies_to: list[str] = Field(default_factory=list)
    status: SkillStatus = "pending"
    source_task: Optional[str] = None
    baseline_metrics: Optional[BaselineMetrics] = None
