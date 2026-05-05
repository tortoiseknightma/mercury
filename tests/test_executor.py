"""Executor node behavior — verified with a fake LLM (no API, no Docker).

We script a sequence of AIMessage responses for the model to return on
successive invocations, then assert how the executor + graph react.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, StateGraph

from mercury.nodes.executor import make_executor_node
from mercury.state import AgentState, new_trace
from mercury.tools import ToolBundle


# ----------------------------------------------------------------- fixtures


class _ScriptedLLM:
    """Returns a pre-scripted AIMessage on each `invoke` call.

    Implements just enough of the BaseChatModel surface that
    `make_executor_node` needs: `bind_tools` returns self, `invoke` pops the
    next scripted message.
    """

    def __init__(self, script: list[AIMessage]) -> None:
        self._script = list(script)
        self.calls: list[list] = []

    def bind_tools(self, _tools, **_kwargs):
        return self

    def invoke(self, messages, *_, **__) -> AIMessage:
        self.calls.append(list(messages))
        if not self._script:
            raise RuntimeError("scripted LLM exhausted")
        return self._script.pop(0)


def _bundle_with(stub_tool) -> ToolBundle:
    """Pack a single stub StructuredTool into a ToolBundle."""
    return ToolBundle(
        python_repl=stub_tool,
        read_file=stub_tool,
        write_file=stub_tool,
        load_skill=stub_tool,
        submit=stub_tool,
    )


def _ai_with_tool_call(tool_name: str, args: dict, tool_call_id: str = "x") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args, "id": tool_call_id, "type": "tool_call"}],
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )


def _ai_text(content: str) -> AIMessage:
    return AIMessage(
        content=content,
        usage_metadata={"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
    )


def _build_app(llm, tools: ToolBundle, max_steps: int):
    node = make_executor_node(llm=llm, tools=tools, max_steps=max_steps)
    g = StateGraph(AgentState)
    g.add_node("executor", node)
    g.set_entry_point("executor")
    g.add_conditional_edges(
        "executor",
        lambda s: END if s.get("done") else "executor",
        {END: END, "executor": "executor"},
    )
    return g.compile()


def _initial_state(task_desc: str = "demo task") -> dict:
    trace = new_trace("test-001", task_desc, "baseline")
    return {
        "task_id": "test-001",
        "task": task_desc,
        "messages": [],
        "scratchpad": {},
        "skill_manifest": [],
        "loaded_skill_bodies": {},
        "trace": trace,
        "consecutive_no_tool": 0,
        "done": False,
    }


# ---------------------------------------------------------- exit condition: submit


def test_submit_pass_terminates_loop() -> None:
    """When `submit` returns passed=True, the loop must stop with success."""
    from langchain_core.tools import StructuredTool

    submitted: dict = {}

    def fake_submit(output_path: str = "out", note: str = "") -> str:
        submitted["called"] = True
        return '{"passed": true, "reason": "ok", "output_path": "out"}'

    submit_tool = StructuredTool.from_function(
        func=fake_submit,
        name="submit",
        description="submit",
    )
    tools = _bundle_with(submit_tool)

    llm = _ScriptedLLM([_ai_with_tool_call("submit", {"output_path": "out"})])
    app = _build_app(llm, tools, max_steps=12)

    final = app.invoke(_initial_state(), config={"recursion_limit": 16})
    assert final["done"] is True
    assert final["trace"]["success"] is True
    assert submitted["called"]


# ---------------------------------------------------------- exit condition: max_steps


def test_max_steps_caps_runaway_agent() -> None:
    """If the model keeps calling tools without ever submitting, max_steps caps it."""
    from langchain_core.tools import StructuredTool

    def noop(code: str = "") -> str:
        return '{"exit_code": 0, "stdout": "", "stderr": ""}'

    noop_tool = StructuredTool.from_function(func=noop, name="python_repl", description="x")
    tools = _bundle_with(noop_tool)

    # Scripted to call python_repl 100 times — will be cut off by max_steps.
    script = [_ai_with_tool_call("python_repl", {"code": "pass"}, tool_call_id=f"t{i}") for i in range(100)]
    llm = _ScriptedLLM(script)

    app = _build_app(llm, tools, max_steps=3)
    final = app.invoke(_initial_state(), config={"recursion_limit": 32})

    assert final["done"] is True
    assert final["trace"]["success"] is False
    assert final["trace"]["total_turns"] == 3, final["trace"]["total_turns"]


# ---------------------------------------------------------- exit condition: stuck on text


def test_three_consecutive_no_tool_terminates() -> None:
    """When the model returns plain text 3 turns in a row, we declare it stuck."""
    from langchain_core.tools import StructuredTool

    def x(*_a, **_kw) -> str:
        return ""

    tool = StructuredTool.from_function(func=x, name="python_repl", description="x")
    tools = _bundle_with(tool)

    llm = _ScriptedLLM([_ai_text("hmm"), _ai_text("thinking"), _ai_text("more thoughts"), _ai_text("never reached")])
    app = _build_app(llm, tools, max_steps=12)

    final = app.invoke(_initial_state(), config={"recursion_limit": 16})
    assert final["done"] is True
    assert final["trace"]["success"] is False
    assert final["consecutive_no_tool"] == 3


def test_consecutive_counter_resets_after_tool_call() -> None:
    """Two text turns then a tool call — the counter resets, no early exit."""
    from langchain_core.tools import StructuredTool

    def fake_submit(**_kw) -> str:
        return '{"passed": true, "reason": "ok", "output_path": "out"}'

    submit_tool = StructuredTool.from_function(func=fake_submit, name="submit", description="x")
    tools = _bundle_with(submit_tool)

    llm = _ScriptedLLM(
        [
            _ai_text("first thought"),
            _ai_text("second thought"),
            _ai_with_tool_call("submit", {}),  # resets counter, also passes
        ]
    )
    app = _build_app(llm, tools, max_steps=12)

    final = app.invoke(_initial_state(), config={"recursion_limit": 16})
    assert final["trace"]["success"] is True
    assert final["consecutive_no_tool"] == 0


# ---------------------------------------------------------- trace shape


def test_trace_records_llm_and_tool_steps() -> None:
    from langchain_core.tools import StructuredTool

    def fake_submit(**_kw) -> str:
        return '{"passed": true, "reason": "ok", "output_path": "out"}'

    submit_tool = StructuredTool.from_function(func=fake_submit, name="submit", description="x")
    tools = _bundle_with(submit_tool)

    llm = _ScriptedLLM([_ai_with_tool_call("submit", {})])
    app = _build_app(llm, tools, max_steps=12)
    final = app.invoke(_initial_state(), config={"recursion_limit": 8})

    steps = final["trace"]["steps"]
    assert [s["tool"] for s in steps] == ["llm", "submit"]
    # LLM step contributes tokens; tool step contributes none (charged via LLM).
    assert final["trace"]["total_tokens"] == 15
    assert final["trace"]["total_turns"] == 1
