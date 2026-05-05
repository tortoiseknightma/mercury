"""LangGraph AgentState + TraceCard schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional, TypedDict

from langgraph.graph.message import add_messages


Mode = Literal["baseline", "evolve", "evolved", "verify"]


class TraceStep(TypedDict):
    step_id: int
    tool: str  # python_repl | read_file | write_file | load_skill | submit | llm
    args: dict[str, Any]
    output: str  # truncated to ~4 KB
    error: Optional[str]
    duration_ms: int
    tokens_in: int
    tokens_out: int


class TraceCard(TypedDict):
    task_id: str
    task_description: str
    mode: Mode
    skills_loaded: list[str]
    steps: list[TraceStep]
    final_output_path: Optional[str]
    success: bool
    total_tokens: int
    total_turns: int
    timestamp: str


class ProposedSkill(TypedDict, total=False):
    should_synthesize: bool
    skill_name: str
    trigger_description: str
    failure_patterns: list[str]
    successful_subroutines: list[str]
    instructions_md: str


class AgentState(TypedDict, total=False):
    # Task identity
    task_id: str
    task: str
    workspace_dir: str
    expected_acceptance: str  # registered fn name; resolved at submit-time

    # Conversation
    messages: Annotated[list, add_messages]

    # Working memory exposed to executor
    scratchpad: dict[str, Any]

    # Skill manifest / loaded bodies
    skill_manifest: list[dict[str, str]]
    loaded_skill_bodies: dict[str, str]

    # Telemetry
    trace: TraceCard

    # Pipeline outputs
    proposed_skill: Optional[ProposedSkill]

    # Loop control (executor internals)
    done: bool                  # set when executor's inner loop should stop
    consecutive_no_tool: int    # how many turns in a row produced no tool_calls

    # Synthesizer output — path to the SKILL.md just written, or None.
    synthesized_skill_path: Optional[str]

    # Verifier output — None if verifier didn't run (no synthesis happened).
    # Otherwise a serialised VerificationOutcome dict.
    verification_outcome: Optional[dict]


def new_trace(task_id: str, task_description: str, mode: Mode) -> TraceCard:
    return TraceCard(
        task_id=task_id,
        task_description=task_description,
        mode=mode,
        skills_loaded=[],
        steps=[],
        final_output_path=None,
        success=False,
        total_tokens=0,
        total_turns=0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def append_step(trace: TraceCard, step: TraceStep) -> None:
    """Mutating append. Caller is responsible for ensuring step_id ordering.

    `total_turns` counts LLM round-trips (one per `tool='llm'` step), which
    is the cost-relevant metric. Tool steps add to `total_tokens` only if
    they happen to charge tokens (currently always 0; future tool kinds may).
    """
    trace["steps"].append(step)
    trace["total_tokens"] += step["tokens_in"] + step["tokens_out"]
    if step["tool"] == "llm":
        trace["total_turns"] += 1
