"""Trace bookkeeping: append + serialize + reload roundtrip."""

from __future__ import annotations

from pathlib import Path

from mercury.state import TraceCard, TraceStep, append_step, new_trace
from mercury.trace import load_trace, save_trace


def test_new_trace_initial_state() -> None:
    t = new_trace("csv-001", "demo desc", "baseline")
    assert t["task_id"] == "csv-001"
    assert t["mode"] == "baseline"
    assert t["steps"] == []
    assert t["total_tokens"] == 0
    assert t["total_turns"] == 0
    assert t["success"] is False


def test_append_step_updates_totals() -> None:
    t = new_trace("csv-001", "demo", "baseline")
    # An LLM step bumps total_turns AND total_tokens.
    llm_step = TraceStep(
        step_id=0,
        tool="llm",
        args={},
        output="",
        error=None,
        duration_ms=200,
        tokens_in=100,
        tokens_out=20,
    )
    append_step(t, llm_step)
    assert t["total_tokens"] == 120
    assert t["total_turns"] == 1
    assert len(t["steps"]) == 1

    # A tool step bumps tokens (0 here) but not turns.
    tool_step = TraceStep(
        step_id=1,
        tool="python_repl",
        args={"code": "print(1)"},
        output="1",
        error=None,
        duration_ms=12,
        tokens_in=0,
        tokens_out=0,
    )
    append_step(t, tool_step)
    assert t["total_turns"] == 1, "tool calls must not bump turn count"
    assert len(t["steps"]) == 2


def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch) -> None:
    import mercury.trace as trace_mod

    monkeypatch.setattr(trace_mod, "TRACES_DIR", tmp_path)

    t = new_trace("csv-001", "demo", "baseline")
    append_step(
        t,
        TraceStep(
            step_id=0,
            tool="python_repl",
            args={"code": "x"},
            output="out",
            error=None,
            duration_ms=5,
            tokens_in=10,
            tokens_out=5,
        ),
    )
    t["success"] = True
    p = save_trace(t)
    assert p.exists()

    reloaded = load_trace(p)
    assert reloaded["task_id"] == t["task_id"]
    assert reloaded["success"] is True
    assert len(reloaded["steps"]) == 1
    assert reloaded["steps"][0]["tool"] == "python_repl"
