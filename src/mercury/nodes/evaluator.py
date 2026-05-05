"""Evaluator node — read the trace, decide whether a reusable skill is in there.

Cheap LLM-as-architect: given the full step-by-step trace of one task run, it
either says "nothing reusable here" (`should_synthesize=false`) or returns a
structured proposal that the synthesizer turns into a SKILL.md.

Triggering policy (graph-level):
- skip when the run was trivially successful (turns < 4 AND success=True)
- always run on failures (failure = teaching opportunity too)
- always run when the agent took ≥ 4 LLM turns (something interesting happened)
"""

from __future__ import annotations

import json
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from mercury.llm import build_llm, invoke_with_retry
from mercury.state import AgentState


# ----------------------------------------------------------------- schema


class ProposedSkillSchema(BaseModel):
    """Structured output for the evaluator. Empty fields when not synthesizing."""

    should_synthesize: bool = Field(
        description=(
            "True if this trace contains a reusable, non-obvious pattern "
            "future agents would benefit from following step-by-step."
        )
    )
    skill_name: Optional[str] = Field(
        default=None,
        description="kebab-case, ≤ 4 words, e.g. `csv-mixed-delim-cleanup`.",
    )
    trigger_description: Optional[str] = Field(
        default=None,
        description=(
            "ONE sentence shown in the manifest. Phrase as: "
            "'When the input is X, use this skill before Y.'"
        ),
    )
    failure_patterns: list[str] = Field(
        default_factory=list,
        description="Short bullets describing wrong turns observed in the trace.",
    )
    successful_subroutines: list[str] = Field(
        default_factory=list,
        description="Short bullets describing the steps that ultimately worked.",
    )
    instructions_md: Optional[str] = Field(
        default=None,
        description=(
            "Markdown body for the SKILL.md, with sections "
            "## When to use, ## Steps, ## Pitfalls."
        ),
    )


# ----------------------------------------------------------------- triggering


MIN_TURNS_FOR_REFLECTION = 4


def should_evaluate(state: AgentState) -> bool:
    """Returns True iff the trace looks worth analysing.

    Pure function — used by graph routing AND by tests.
    """
    trace = state.get("trace") or {}
    turns = trace.get("total_turns", 0)
    success = trace.get("success", False)
    if not success:
        return True
    return turns >= MIN_TURNS_FOR_REFLECTION


# ----------------------------------------------------------------- prompt


SYSTEM = """\
You are a senior AI architect reviewing an agent's execution trace. You decide \
whether the trace contains a *reusable* pattern worth saving as an Agent Skill.

A good skill captures a non-obvious SOP — something a fresh agent would likely \
fail at on their first attempt. If the trace shows the agent solved the task \
in 1–2 turns with the obvious approach, do NOT propose a skill. \
If it shows retries, dead-ends, or domain-specific tricks that worked, DO \
propose one and articulate it crisply.

Output strictly via the structured schema. When `should_synthesize=false`, \
leave the other fields empty. When `should_synthesize=true`, produce ALL of: \
skill_name, trigger_description, failure_patterns, successful_subroutines, \
instructions_md.

Skill names: kebab-case, ≤ 4 words, e.g. `csv-mixed-delim-cleanup`. \
Trigger descriptions: ONE sentence, "When ... use this skill before ...". \
Instructions: markdown with `## When to use`, `## Steps`, `## Pitfalls`.
"""


def _summarise_trace(state: AgentState) -> str:
    trace = state["trace"]
    lines: list[str] = []
    for step in trace.get("steps", []):
        sid = step.get("step_id", "?")
        tool = step.get("tool", "?")
        if tool == "llm":
            content = (step.get("output") or "").strip()
            if not content:
                lines.append(f"[{sid}] LLM: <emitted tool calls>")
            else:
                lines.append(f"[{sid}] LLM: {content[:240]}")
        else:
            args = json.dumps(step.get("args") or {}, ensure_ascii=False)[:160]
            out = (step.get("output") or "").strip()[:240]
            err = step.get("error")
            tail = f" ERROR={err}" if err else ""
            lines.append(f"[{sid}] {tool}({args}) -> {out}{tail}")
    return "\n".join(lines)


def _build_user_message(state: AgentState) -> str:
    trace = state["trace"]
    return (
        f"# Task\n{trace['task_description']}\n\n"
        f"# Outcome: {'SUCCESS' if trace.get('success') else 'FAILURE'}\n"
        f"Turns: {trace.get('total_turns', 0)}, "
        f"Tokens: {trace.get('total_tokens', 0)}\n\n"
        f"# Step-by-step trace\n{_summarise_trace(state)}\n"
    )


# ----------------------------------------------------------------- node


def _emit_proposal_tool() -> StructuredTool:
    """A no-op tool whose schema IS the structured output we want.

    We bind this as a regular tool (NOT via `with_structured_output`, which
    would set tool_choice="required" and conflict with Qwen's thinking mode)
    and pull the model's structured args out of `response.tool_calls[0]`.
    """

    def _noop(**kwargs):  # noqa: ANN003
        return kwargs

    return StructuredTool.from_function(
        func=_noop,
        name="emit_skill_proposal",
        description=(
            "Emit your structured analysis of the trace. ALWAYS call this "
            "tool exactly once to deliver your verdict — do not reply in "
            "free text."
        ),
        args_schema=ProposedSkillSchema,
    )


def _coerce_proposal(raw: dict) -> dict:
    """Validate raw LLM tool args via Pydantic, returning a normalized dict."""
    try:
        return ProposedSkillSchema(**raw).model_dump()
    except Exception:  # noqa: BLE001
        # Best-effort fallback: keep what we got, mark as unsafe to synthesize.
        return {"should_synthesize": False, "_error": "schema validation failed"}


def make_evaluator_node(
    llm: Optional[ChatOpenAI] = None,
    flash_llm: Optional[ChatOpenAI] = None,
):
    if llm is None:
        llm = build_llm("evaluator")
    if flash_llm is None:
        flash_llm = build_llm("flash")

    proposal_tool = _emit_proposal_tool()
    llm_with_tool = llm.bind_tools([proposal_tool])

    def evaluator_node(state: AgentState) -> dict:
        if not should_evaluate(state):
            return {"proposed_skill": {"should_synthesize": False}}

        user_msg = _build_user_message(state)

        # Flash pre-screen
        flash_messages = [
            SystemMessage(
                content="You are a quick filter. Look at this agent execution trace. "
                "Did the agent encounter ANY errors, or use more than 4 turns to solve the problem? "
                "If so, reply exactly YES, otherwise NO."
            ),
            HumanMessage(content=user_msg),
        ]
        try:
            flash_response = invoke_with_retry(flash_llm, flash_messages)
            content = (getattr(flash_response, "content", "") or "").strip().upper()
            if "YES" not in content:
                return {
                    "proposed_skill": {
                        "should_synthesize": False,
                        "_note": "flash pre-screen rejected",
                    }
                }
        except Exception:
            pass  # Fallback to full evaluation on flash failure

        messages = [
            SystemMessage(content=SYSTEM),
            HumanMessage(content=user_msg),
        ]
        try:
            response = invoke_with_retry(llm_with_tool, messages)
        except Exception as e:  # noqa: BLE001
            return {
                "proposed_skill": {
                    "should_synthesize": False,
                    "_error": f"evaluator LLM call failed: {e}",
                }
            }

        tool_calls = list(getattr(response, "tool_calls", []) or [])
        if not tool_calls:
            # Model replied in plain text — try to recover JSON from it, else skip.
            content = (getattr(response, "content", "") or "").strip()
            try:
                payload = json.loads(content)
                if isinstance(payload, dict):
                    return {"proposed_skill": _coerce_proposal(payload)}
            except (json.JSONDecodeError, TypeError):
                pass
            return {
                "proposed_skill": {
                    "should_synthesize": False,
                    "_error": "evaluator returned no tool call",
                }
            }

        # Take the first matching call. Defensive: ignore other tools.
        for tc in tool_calls:
            if tc.get("name") == "emit_skill_proposal":
                return {"proposed_skill": _coerce_proposal(tc.get("args") or {})}

        return {
            "proposed_skill": {
                "should_synthesize": False,
                "_error": f"unexpected tool calls: {[tc.get('name') for tc in tool_calls]}",
            }
        }

    return evaluator_node
