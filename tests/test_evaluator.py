"""Evaluator gating + structured output handling — no real LLM.

The evaluator binds an `emit_skill_proposal` tool and reads the model's
structured output from `response.tool_calls[0].args`. Tests stub the LLM
with that surface (`bind_tools` + `invoke` returning an `AIMessage`).
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from mercury.nodes.evaluator import (
    MIN_TURNS_FOR_REFLECTION,
    ProposedSkillSchema,
    make_evaluator_node,
    should_evaluate,
)
from mercury.state import new_trace


def _state(*, success: bool, turns: int) -> dict:
    trace = new_trace("csv-001", "demo task", "evolve")
    trace["success"] = success
    trace["total_turns"] = turns
    trace["steps"] = [
        {
            "step_id": 0,
            "tool": "llm",
            "args": {},
            "output": "thinking",
            "error": None,
            "duration_ms": 100,
            "tokens_in": 50,
            "tokens_out": 10,
        }
    ]
    return {"task_id": "csv-001", "trace": trace}


# --------------------------------------------------------------------- gating


def test_skip_when_trivially_successful() -> None:
    assert should_evaluate(_state(success=True, turns=2)) is False


def test_run_on_long_success() -> None:
    assert should_evaluate(_state(success=True, turns=MIN_TURNS_FOR_REFLECTION)) is True


def test_always_run_on_failure() -> None:
    assert should_evaluate(_state(success=False, turns=1)) is True


# --------------------------------------------------------------- structured output


class _StubLLM:
    """Stand-in for ChatOpenAI: `bind_tools` + `invoke` returning AIMessage.

    The evaluator binds a tool, then reads `response.tool_calls[0].args`. So a
    stub just needs to (a) accept `bind_tools` and (b) yield a pre-scripted
    `AIMessage` (or raise) on `invoke`.
    """

    def __init__(self, response: AIMessage | Exception) -> None:
        self._response = response
        self.calls = 0

    def bind_tools(self, _tools, **_kw):  # noqa: ARG002
        return self

    def invoke(self, _messages, *_args, **_kw) -> AIMessage:
        self.calls += 1
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _ai_with_proposal(args: dict) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "emit_skill_proposal", "args": args, "id": "p1", "type": "tool_call"}
        ],
    )


def test_evaluator_short_circuits_when_not_worth_it() -> None:
    """Gate trips before LLM call — LLM must never be invoked."""
    llm = _StubLLM(_ai_with_proposal({"should_synthesize": True, "skill_name": "x"}))
    node = make_evaluator_node(llm=llm, flash_llm=_StubLLM(AIMessage(content="YES")))  # type: ignore[arg-type]

    out = node(_state(success=True, turns=2))
    assert out["proposed_skill"]["should_synthesize"] is False
    assert llm.calls == 0, "LLM must NOT be called when gate says skip"


def test_evaluator_propagates_structured_payload() -> None:
    """Structured tool args flow through to the proposed_skill output."""
    payload = {
        "should_synthesize": True,
        "skill_name": "csv-mixed-delim-cleanup",
        "trigger_description": "When the CSV has mixed delimiters, do X.",
        "failure_patterns": ["UnicodeDecodeError on naive utf-8 read"],
        "successful_subroutines": ["csv.Sniffer for delimiter detection"],
        "instructions_md": "## When to use\nfoo",
    }
    llm = _StubLLM(_ai_with_proposal(payload))
    node = make_evaluator_node(llm=llm, flash_llm=_StubLLM(AIMessage(content="YES")))  # type: ignore[arg-type]

    out = node(_state(success=True, turns=6))
    proposed = out["proposed_skill"]
    assert proposed["should_synthesize"] is True
    assert proposed["skill_name"] == "csv-mixed-delim-cleanup"
    assert "delimiters" in proposed["trigger_description"]
    assert llm.calls == 1


def test_evaluator_swallows_llm_errors() -> None:
    """Transient LLM failure should not crash the run — just opt out of synthesis."""
    llm = _StubLLM(RuntimeError("dashscope timeout"))
    node = make_evaluator_node(llm=llm, flash_llm=_StubLLM(AIMessage(content="YES")))  # type: ignore[arg-type]

    out = node(_state(success=False, turns=1))
    assert out["proposed_skill"]["should_synthesize"] is False
    assert "_error" in out["proposed_skill"]


def test_evaluator_recovers_from_plain_text_json() -> None:
    """If the model replies in free text but emits valid JSON, parse it as fallback."""
    payload = {
        "should_synthesize": True,
        "skill_name": "json-flatten",
        "trigger_description": "When the JSON is deeply nested, flatten before pivoting.",
        "failure_patterns": ["KeyError on nested access"],
        "successful_subroutines": ["pd.json_normalize"],
        "instructions_md": "## When to use\nuse json_normalize",
    }
    import json as _json

    llm = _StubLLM(AIMessage(content=_json.dumps(payload)))
    node = make_evaluator_node(llm=llm, flash_llm=_StubLLM(AIMessage(content="YES")))  # type: ignore[arg-type]

    out = node(_state(success=True, turns=5))
    assert out["proposed_skill"]["should_synthesize"] is True
    assert out["proposed_skill"]["skill_name"] == "json-flatten"


def test_evaluator_marks_error_when_no_tool_call_and_no_json() -> None:
    """No tool call AND non-JSON content → graceful skip with _error annotation."""
    llm = _StubLLM(AIMessage(content="I think we should do something but I'm not sure."))
    node = make_evaluator_node(llm=llm, flash_llm=_StubLLM(AIMessage(content="YES")))  # type: ignore[arg-type]

    out = node(_state(success=False, turns=2))
    assert out["proposed_skill"]["should_synthesize"] is False
    assert "_error" in out["proposed_skill"]


def test_evaluator_flash_prescreen_rejects() -> None:
    """If flash_llm replies NO, the main llm is never invoked."""
    llm = _StubLLM(AIMessage(content="FAIL IF CALLED"))
    flash_llm = _StubLLM(AIMessage(content="NO. This is not interesting."))
    node = make_evaluator_node(llm=llm, flash_llm=flash_llm)  # type: ignore[arg-type]

    out = node(_state(success=True, turns=5))
    assert out["proposed_skill"]["should_synthesize"] is False
    assert out["proposed_skill"]["_note"] == "flash pre-screen rejected"
    assert llm.calls == 0
