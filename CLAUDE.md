# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Mercury is a 1-week sprint (Day 1-7 ✅ delivered) building a self-evolving skill-synthesis agent (LangGraph + Anthropic-spec Agent Skills). Status and per-day produce-and-learnings live in `ROADMAP.md` — **read it first** when picking up a session, since it tracks which Day-N milestones are done and the discovered findings of each (e.g. Day 6's "skill regression" diagnosis).

Design rationale and the originating proposal: `docs/Agent 项目构思与选型.md`. Module-level technical reference: `docs/architecture.md`. Resume narrative + interview Q&A: `docs/RESUME.md`. Headline benchmark numbers: `docs/BENCHMARK_SUMMARY.md`.

## Commands

```powershell
# Install + sync deps (uv auto-installs Python 3.12; requires-python is >=3.11,<3.13)
uv sync

# Build / refresh the sandbox image (REQUIRED — the agent can't run without it).
# We use a custom image because the container runs with network=none, so pip-at-runtime is impossible.
uv run python scripts/pull_docker_image.py

# Offline tests only (139 passed; skips Docker / real-LLM tests)
uv run pytest tests/ --ignore=tests/test_sandbox.py --ignore=tests/test_tools_e2e.py --ignore=tests/test_llm.py

# Full test suite (also runs Docker integration + real DashScope smoke)
uv run pytest tests/

# Single test file / single test
uv run pytest tests/test_executor.py
uv run pytest tests/test_executor.py::test_submit_pass_terminates_loop

# Run a real task end-to-end (needs DASHSCOPE_API_KEY in .env + Docker running)
uv run mercury run --task csv-001 --mode baseline
uv run mercury run --task csv-001 --mode evolve     # executor + evaluator + synthesizer + verifier inline
uv run mercury list-tasks

# Full evaluation pipeline (≈80–150K tokens, prompt cache mitigates re-runs)
uv run mercury reset                                # wipe library + state.db
uv run mercury bench --mode baseline                # → results/metrics_baseline.json
uv run mercury evolve                               # synth + inline verify
uv run mercury bench --mode evolved                 # → results/metrics_evolved.json
uv run mercury report                               # comparison table + 3 PNGs
```

`.env` is required for any LLM-touching command but **not** auto-loaded by pytest — tests that need it call `load_dotenv()` themselves (see `tests/test_llm.py`). `tests/test_sandbox.py` and `tests/test_tools_e2e.py` need Docker running.

## Architecture

The agent is a LangGraph `StateGraph` over `AgentState` (TypedDict in `src/mercury/state.py`) with a `SqliteSaver` checkpointer at `results/state.db`.

```
            ┌──────────┐
       ┌───▶│ executor │───┐
   loop│    └──────────┘   │ done / timeout
       │                   ▼
       │              ┌──────────┐    propose      ┌─────────────┐    write     ┌──────────┐
       └──────────────│evaluator │────────────────▶│ synthesizer │─────────────▶│ verifier │
                      └──────────┘                 └─────────────┘              └────┬─────┘
                            │ skip                                                   │
                            ▼                                                        ▼
                           END                                              status: verified | rejected
```

- **`nodes/executor.py`** — one LLM call + tool execution per invocation; the graph self-loops until `done`. Three exit conditions: `submit` returned `passed=True`, `total_turns >= max_steps`, or 3 consecutive turns produced no tool calls. Tool calls execute inline; the trace records each step.
- **`nodes/evaluator.py`** — runs only in `evolve` mode after the executor finishes. `should_evaluate(state)` gates entry: skip trivial successes (`turns < 4 ∧ success`), always reflect on failures and on long traces. The evaluator emits a structured proposal via a `bind_tools([emit_skill_proposal])` workaround (Qwen tool-call mode conflicts with LangChain's `with_structured_output(tool_choice="required")`).
- **`nodes/synthesizer.py`** — pure I/O, no LLM. Sanitises the skill name to kebab-case, writes `skills/library/<name>/SKILL.md` with `status: pending` + `baseline_metrics`. Idempotent: never overwrites.
- **`nodes/verifier.py`** — replays source task + a same-group neighbour + a cross-group anti-trigger task. Three-axis gate: source must satisfy `success ∧ tokens ≤ 0.85 × baseline_tokens ∧ turns ≤ baseline_turns`; neighbour must `success`; anti-trigger task must NOT call `load_skill(<this-skill>)` (broad-trigger detection). Promotes frontmatter to `verified` on pass; archives to `_rejected/<name>__<ts>/` with a `rejection.json` post-mortem on fail. The probe runner deliberately reuses `EXECUTOR_MODEL` so the 0.85× budget stays comparable to recorded baseline_metrics.

`graph.py::build_app()` is the single entry point that wires the right edges per mode (`baseline` | `evolve` | `evolved`). It returns `(app, last_acceptance, conn)` — the caller MUST `conn.close()` the SqliteSaver connection (see `cli.py::run`).

### Tools (`src/mercury/tools.py`)

5 `StructuredTool`s built per-run via `build_tools()` so they close over task-specific state:
- `python_repl` → forwards to `SandboxBackend.run()`; output truncated to 4 KB.
- `read_file`, `write_file` → workspace-scoped (rejects path-escapes).
- `load_skill` → calls `skills/loader.py::load_full`. In `baseline` mode the manifest is empty; only `evolved` mode injects verified skills.
- `submit` → invokes the task's `accept()` callable on the host; returns `{passed, reason, output_path}`.

Tool outputs in tests/non-Docker contexts must be JSON strings — the executor parses `submit`'s result with `json.loads` to detect success.

### Skills (Anthropic Agent Skills format)

`skills/library/<name>/SKILL.md` is YAML frontmatter (`SkillFrontmatter` pydantic model) + markdown body. **Progressive disclosure**: at startup only `(name, description)` pairs are injected into the system prompt; full body loads on demand via the `load_skill` tool. The manifest scan (`scan_manifest`) defaults to `status="verified"`, so `pending` skills are invisible until the verifier promotes them.

### Tasks (`src/mercury/eval/tasks/`)

Each task lives at `<group>/<id>/` with `task.py` (defines `TASK = register(Task(...))` and an `accept(workspace) -> (bool, str)`), an input file, and an `expected.*` ground truth. **Acceptance is always deterministic Python — never an LLM judge.** The registry auto-discovers tasks on first `all_tasks()` / `get_task()` call. `expected.*` stays on the host and is never copied into the workspace exposed to the agent.

Current task set: 16 tasks across 6 groups — `csv` (5), `json` (2), `log` (2), `multi` (2, cross-file JOIN + GBK), `pipeline` (3, chained transforms / Z-score), `xml` (2, including a deliberately-broken document for repair).

### Eval pipeline (`src/mercury/eval/`)

`runner.run_one_task` / `runner.run_bench` drive the same machinery `mercury run` uses but in pure-function form (no console output, no `sys.exit`). `metrics.compute` aggregates a `BenchResult` into `BenchMetrics` (Pass@1, avg_tokens, avg_turns, by_group split). `metrics.normalized_gain(p_before, p_after)` clamps to 0 when `p_before == 1.0`. `plots.render_all(baseline, evolved)` produces 3 figures (grouped bars / per-task line / token radar; radar auto-falls-back to a line plot when fewer than 3 tasks are present).

### Sandbox (`src/mercury/sandbox/docker_sandbox.py`)

Long-lived container per task (`sleep infinity` + `exec_run` per snippet — much cheaper than a fresh container per call). Workspace bind-mounted at `/workspace`. Hardening: `network=none`, `mem<=512m`, `nano_cpus=1e9`, `cap_drop=ALL`, `security_opt=no-new-privileges`, `pids_limit=128`. Per-call timeout enforced with GNU `timeout --signal=KILL`; treat exit codes 124/137 as `timed_out=True`. Image is `mercury-sandbox:latest` (built locally), not `python:3.11-slim`.

## Conventions worth knowing

- **Per-role models**: `EXECUTOR_MODEL` / `EVALUATOR_MODEL` / `FLASH_MODEL` env vars override per role; each falls back to `QWEN_PLUS_MODEL` (or `QWEN_FLASH_MODEL` for the third). The verifier's probe runs deliberately reuse `EXECUTOR_MODEL` — baseline_metrics were measured on that model, so the 0.85× token budget is only meaningful if probes use the same one. Point `EXECUTOR_MODEL` at a weaker model (qwen-flash / qwen-turbo) to lengthen traces and give the evaluator more material to reflect on.
- **Global prompt cache**: `llm.py` calls `set_llm_cache(SQLiteCache(results/prompt_cache.db))` at import time. Identical `(model, messages, params)` tuples are served from the cache at zero cost. Delete the file to force a clean re-bench.
- **`total_turns` counts LLM round-trips**, not graph steps — `append_step` only increments it for `tool == "llm"` steps. Don't conflate with `len(steps)`.
- **`recursion_limit=64`** must be passed in `app.invoke(..., config={"recursion_limit": 64})` because the executor's tool round-trips burn through the LangGraph default of 25 fast.
- **Conditional edges need an explicit mapping dict**, otherwise LangGraph treats the routing function's return string as a literal node name. See `graph.py`.
- **Windows quirks** — the CLI reconfigures `sys.stdout` to UTF-8 (cp936/gbk default mangles rich's output). Docker SDK's `dockerfile=` argument needs POSIX paths (`Path.as_posix()`).
- **uv resolves Python 3.12.13** within the `>=3.11,<3.13` bound; that's expected, not a misconfiguration.
- **`langgraph-checkpoint-sqlite`** is a separate package from `langgraph` post-0.2 — keep it in `pyproject.toml`.
- **Three-axis admission gate (Day 4)**: `success ∧ tokens ≤ 0.85 × baseline ∧ turns ≤ baseline`. Encoded in `SkillFrontmatter.baseline_metrics`. Never weaken without updating the roadmap.

## Code style

- `from __future__ import annotations` at the top of every module.
- Pydantic v2; `BaseModel` for structured data, `Field(description=...)` for LLM-visible schemas.
- `dataclass(frozen=True)` for config; `TypedDict` for LangGraph state.
- Ruff line-length 100, target-version py311.
- Tests use plain `pytest` + `GenericFakeChatModel` / a small `_ScriptedLLM` for executor tests — no real network calls except in `test_llm.py` and `test_tools_e2e.py`.
