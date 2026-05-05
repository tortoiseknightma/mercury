"""Executor node — one LLM step + tool execution + trace bookkeeping.

Each invocation of `executor_node` corresponds to ONE LLM call followed by
inline execution of any tool calls the model produced. The graph then loops
back to this node until one of the exit conditions trips:

  - submit returned passed=True
  - total turns >= max_steps
  - 3 consecutive turns produced no tool calls (the model is stuck talking)

The node is built by a factory (`make_executor_node`) so it can close over
per-task state — the LLM client, the tool bundle, and step caps.
"""

from __future__ import annotations

import json
import time
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.language_models import BaseChatModel

from mercury.llm import invoke_with_retry
from mercury.state import AgentState, TraceStep, append_step
from mercury.tools import ToolBundle


SYSTEM_PROMPT_TEMPLATE = """\
You are Mercury, a data-wrangling agent operating in an isolated Linux workspace at /workspace.

# Tools
- `python_repl(code)`: run Python in a sandboxed container (network=none, mem<=512m, 30s timeout). Pre-installed: pandas, numpy, lxml, beautifulsoup4, chardet, regex, python-dateutil. STATELESS — re-import modules each call.
- `read_file(path, max_bytes=4096)`: peek at a file's content. Returns JSON with `content` (utf-8 text) or `content_hex` (binary).
- `write_file(path, content)`: write UTF-8 text to a workspace file.
- `load_skill(name)`: load detailed instructions for a previously-verified skill from the manifest below.
- `submit(output_path, note="")`: declare the task complete. Triggers the deterministic acceptance check. Returns JSON with `passed` (bool) and `reason`. If `passed=false`, you MAY continue iterating and call `submit` again.

# Verified skills available
{manifest}

# Workflow
1. Read the task description carefully.
2. Use `read_file` or `python_repl` to inspect the input.
3. Write Python in `python_repl` to transform the data and save the output (typical name: `output.csv`).
4. Call `submit` with the output path. If `passed=false`, debug and retry.

# Hard limits
- {max_steps} total turns for this task.
- The container has NO network access.
- Always finish by calling `submit` — silent termination counts as failure.
"""


def _format_manifest(manifest: list[dict[str, str]]) -> str:
    if not manifest:
        return "_No verified skills yet._"
    lines = []
    for s in manifest:
        lines.append(f"- **{s.get('name', '?')}** — {s.get('description', '')}")
    return "\n".join(lines) + "\n\nCall `load_skill(name)` to load full instructions."


def _safe_str(x) -> str:
    try:
        return str(x)
    except Exception:  # noqa: BLE001
        return "<unprintable>"


def make_executor_node(
    *,
    llm: BaseChatModel,
    tools: ToolBundle,
    max_steps: int,
):
    tool_list = tools.as_list()
    tool_map = {t.name: t for t in tool_list}
    llm_with_tools = llm.bind_tools(tool_list)

    def executor_node(state: AgentState) -> dict:
        trace = state["trace"]
        manifest = state.get("skill_manifest") or []
        new_messages: list = []

        # First turn: inject system prompt + initial human task message.
        is_first_turn = not state.get("messages")
        if is_first_turn:
            sys_text = SYSTEM_PROMPT_TEMPLATE.format(
                manifest=_format_manifest(manifest),
                max_steps=max_steps,
            )
            new_messages.append(SystemMessage(content=sys_text))
            new_messages.append(HumanMessage(content=f"Task: {state['task']}"))

        # Compose what we send to the model.
        history = list(state.get("messages") or [])
        messages_for_invoke = history + new_messages

        # ---- LLM call ---------------------------------------------------------
        t0 = time.perf_counter()
        ai_msg: AIMessage = invoke_with_retry(llm_with_tools, messages_for_invoke)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        usage = getattr(ai_msg, "usage_metadata", None) or {}
        tokens_in = int(usage.get("input_tokens", 0))
        tokens_out = int(usage.get("output_tokens", 0))

        llm_step = TraceStep(
            step_id=len(trace["steps"]),
            tool="llm",
            args={"history_len": len(messages_for_invoke)},
            output=(_safe_str(ai_msg.content) or "")[:512],
            error=None,
            duration_ms=elapsed_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        append_step(trace, llm_step)
        new_messages.append(ai_msg)

        # ---- Tool execution ---------------------------------------------------
        consecutive_no_tool = int(state.get("consecutive_no_tool") or 0)
        done = False
        tool_calls = list(getattr(ai_msg, "tool_calls", []) or [])

        if not tool_calls:
            consecutive_no_tool += 1
            if consecutive_no_tool >= 3:
                done = True
        else:
            consecutive_no_tool = 0
            for tc in tool_calls:
                name = tc["name"]
                args = tc.get("args", {}) or {}
                tool_call_id = tc.get("id")

                tool = tool_map.get(name)
                if tool is None:
                    err = f"unknown tool: {name}"
                    new_messages.append(
                        ToolMessage(content=json.dumps({"error": err}), tool_call_id=tool_call_id)
                    )
                    append_step(
                        trace,
                        TraceStep(
                            step_id=len(trace["steps"]),
                            tool=name,
                            args=args,
                            output="",
                            error=err,
                            duration_ms=0,
                            tokens_in=0,
                            tokens_out=0,
                        ),
                    )
                    continue

                t0 = time.perf_counter()
                try:
                    result = tool.invoke(args)
                    err = None
                except Exception as e:  # noqa: BLE001
                    result = json.dumps({"error": str(e)})
                    err = str(e)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)

                result_str = _safe_str(result)
                new_messages.append(ToolMessage(content=result_str, tool_call_id=tool_call_id))
                append_step(
                    trace,
                    TraceStep(
                        step_id=len(trace["steps"]),
                        tool=name,
                        args=args,
                        output=result_str[:1024],
                        error=err,
                        duration_ms=elapsed_ms,
                        tokens_in=0,
                        tokens_out=0,
                    ),
                )

                # Submit success ends the run.
                if name == "submit" and err is None:
                    try:
                        parsed = json.loads(result_str)
                    except (json.JSONDecodeError, TypeError):
                        parsed = None
                    if isinstance(parsed, dict) and parsed.get("passed"):
                        trace["success"] = True
                        trace["final_output_path"] = parsed.get("output_path")
                        done = True

        # Hard cap on turns.
        if trace["total_turns"] >= max_steps:
            done = True

        return {
            "messages": new_messages,
            "trace": trace,
            "consecutive_no_tool": consecutive_no_tool,
            "done": done,
        }

    return executor_node
