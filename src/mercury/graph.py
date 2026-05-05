"""LangGraph assembly.

Day 2: `executor → END` with self-loop until done.
Day 3: in `evolve` mode, also run `evaluator → synthesizer → END` after the
       executor finishes (gated by `should_evaluate`).
Day 4: in `evolve` mode, route synthesizer → verifier → END whenever a
       SKILL.md was actually written.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable, Literal

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from mercury.config import RESULTS_DIR, load_config
from mercury.llm import build_llm
from mercury.nodes.evaluator import make_evaluator_node, should_evaluate
from mercury.nodes.executor import make_executor_node
from mercury.nodes.synthesizer import make_synthesizer_node
from mercury.nodes.verifier import make_verifier_node
from mercury.sandbox import SandboxBackend
from mercury.skills.loader import load_full as load_skill_full
from mercury.state import AgentState
from mercury.tools import build_tools


AcceptFn = Callable[[Path], tuple[bool, str]]
Mode = Literal["baseline", "evolve", "evolved"]


def build_app(
    *,
    workspace: Path,
    sandbox: SandboxBackend,
    accept_fn: AcceptFn,
    mode: Mode = "baseline",
    task_group: str | None = None,
    db_path: Path | None = None,
) -> tuple[Any, dict, Any]:
    """Construct a compiled LangGraph application for one task run.

    Returns:
        (app, last_acceptance, conn_holder)
        - `app`: compiled LangGraph
        - `last_acceptance`: dict mutated in place when `submit` fires
        - `conn_holder`: sqlite3 connection backing the checkpointer.
          Caller MUST `conn_holder.close()` when finished.
    """
    cfg = load_config()
    llm = build_llm("executor")

    last_acceptance: dict = {"passed": False, "reason": "", "output_path": ""}

    def on_submit(output_path: str, note: str) -> dict:
        passed, reason = accept_fn(workspace)
        last_acceptance["passed"] = passed
        last_acceptance["reason"] = reason
        last_acceptance["output_path"] = output_path
        return {"passed": passed, "reason": reason, "output_path": output_path}

    tools = build_tools(
        workspace=workspace,
        sandbox=sandbox,
        skill_loader=load_skill_full,
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

    if mode == "evolve":
        graph.add_node("evaluator", make_evaluator_node())
        graph.add_node("synthesizer", make_synthesizer_node(task_group=task_group))
        graph.add_node("verifier", make_verifier_node())

        graph.add_conditional_edges(
            "executor",
            _route_after_executor_evolve,
            {"executor": "executor", "evaluator": "evaluator", END: END},
        )
        graph.add_conditional_edges(
            "evaluator",
            _route_after_evaluator,
            {"synthesizer": "synthesizer", END: END},
        )
        graph.add_conditional_edges(
            "synthesizer",
            _route_after_synthesizer,
            {"verifier": "verifier", END: END},
        )
        graph.add_edge("verifier", END)
    else:
        graph.add_conditional_edges(
            "executor",
            lambda s: END if s.get("done") else "executor",
            {END: END, "executor": "executor"},
        )

    db_path = db_path or (RESULTS_DIR / "state.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    saver = SqliteSaver(conn)

    app = graph.compile(checkpointer=saver)
    return app, last_acceptance, conn


def _route_after_executor_evolve(state: AgentState) -> str:
    if not state.get("done"):
        return "executor"
    return "evaluator" if should_evaluate(state) else END


def _route_after_evaluator(state: AgentState) -> str:
    proposed = state.get("proposed_skill") or {}
    return "synthesizer" if proposed.get("should_synthesize") else END


def _route_after_synthesizer(state: AgentState) -> str:
    return "verifier" if state.get("synthesized_skill_path") else END
