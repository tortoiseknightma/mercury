# Mercury — Architecture Reference

Module-by-module deep dive. Read this when you need to **modify** the agent;
read [`README.md`](../README.md) for the high-level pitch and headline numbers,
[`BENCHMARK_SUMMARY.md`](./BENCHMARK_SUMMARY.md) for the evaluation results, and
[`RESUME.md`](./RESUME.md) for the interview-facing narrative.

---

## 1. Module map

| File                                           | Role                                                          | Notes                                       |
| ---------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------- |
| `src/mercury/state.py`                         | `AgentState` TypedDict, `TraceCard` / `TraceStep` schemas     | Single source of truth for cross-node data  |
| `src/mercury/graph.py`                         | `build_app()` — compiles the StateGraph for a given mode      | Returns `(app, last_acceptance, conn)`      |
| `src/mercury/nodes/executor.py`                | One LLM call + tool execution per invocation                  | Self-loops via conditional edge             |
| `src/mercury/nodes/evaluator.py`               | Reflects on the trace, proposes a skill                       | `bind_tools([emit_skill_proposal])` — see §6 |
| `src/mercury/nodes/synthesizer.py`             | Pure I/O: writes `SKILL.md` with `status: pending`            | Idempotent — never overwrites               |
| `src/mercury/nodes/verifier.py`                | Three-axis gate + anti-trigger probe + frontmatter promotion  | Spawns a fresh sandbox per probe            |
| `src/mercury/sandbox/docker_sandbox.py`        | `DockerSandbox` — long-lived container + `exec_run`           | Workspace bind-mounted at `/workspace`      |
| `src/mercury/tools.py`                         | 5 `StructuredTool`s built per run via `build_tools()`         | Closes over workspace / sandbox / loader    |
| `src/mercury/skills/{schema,loader}.py`        | Pydantic schemas + parse / scan / `load_full` for SKILL.md    | Progressive-disclosure entry point          |
| `src/mercury/eval/runner.py`                   | `run_one_task` / `run_bench` / `save_bench` / `load_bench`    | Used by both `mercury bench` and `mercury report` |
| `src/mercury/eval/metrics.py`                  | `compute`, `normalized_gain`, `compare`                       | Pure functions — fully unit-tested          |
| `src/mercury/eval/plots.py`                    | 3 figures (Pass@1 bars / token line / token radar)            | `matplotlib.use("Agg")` for headless        |
| `src/mercury/eval/tasks/<group>/<id>/task.py`  | One task definition (description + `accept(workspace)` fn)    | Auto-discovered via `_autodiscover()`       |
| `src/mercury/cli.py`                           | typer wiring                                                  | Forces UTF-8 stdio on Windows               |
| `src/mercury/llm.py`                           | `build_llm(role)` — role-based model dispatch + global cache  | `set_llm_cache(SQLiteCache(...))` at import |
| `src/mercury/config.py`                        | env loading + `LLMConfig` / `SandboxConfig` / `HarnessConfig` | Frozen dataclasses — re-read each call      |

---

## 2. AgentState (`src/mercury/state.py`)

LangGraph routes a single `TypedDict` between nodes. Every field has exactly one *writer* (the node that owns it) and any number of *readers*.

| Field                       | Writer        | Type                          | Purpose                                                |
| --------------------------- | ------------- | ----------------------------- | ------------------------------------------------------ |
| `task_id`, `task`, `workspace_dir`, `expected_acceptance` | caller (CLI / runner) | str | Set once at `app.invoke`            |
| `messages`                  | executor      | `list[BaseMessage]` (`add_messages` reducer) | LangGraph appends — DON'T overwrite |
| `scratchpad`                | reserved      | `dict`                        | Currently unused; reserved for tools to stash blobs    |
| `skill_manifest`            | caller        | `list[dict[str, str]]`        | `[{name, description}]` injected into system prompt    |
| `loaded_skill_bodies`       | (informational) | `dict[str, str]`            | Mirrors `load_skill` calls; never read by routing      |
| `trace`                     | executor      | `TraceCard`                   | Mutated in place via `append_step` — see §3             |
| `proposed_skill`            | evaluator     | `Optional[ProposedSkill]`     | Routes synthesis on / off                              |
| `done`                      | executor      | `bool`                        | Routes inner loop on / off                             |
| `consecutive_no_tool`       | executor      | `int`                         | Stuck-detector counter (3 in a row → done)             |
| `synthesized_skill_path`    | synthesizer   | `Optional[str]`               | Routes verifier on / off                               |
| `verification_outcome`      | verifier      | `Optional[dict]`              | Serialised `VerificationOutcome` for CLI summary       |

### TraceCard schema

```
TraceCard = {
    task_id, task_description, mode, skills_loaded[],
    steps: list[TraceStep],
    final_output_path, success,
    total_tokens, total_turns,    # turns counts ONLY tool=='llm' steps
    timestamp,
}

TraceStep = {
    step_id, tool, args, output,
    error, duration_ms,
    tokens_in, tokens_out,
}
```

`append_step` increments `total_turns` only when `step["tool"] == "llm"`. This is the cost-relevant metric and must not be conflated with `len(steps)` (which counts LLM rounds *and* every tool invocation inside them).

---

## 3. Graph routing (`src/mercury/graph.py::build_app`)

Three modes, each compiling a different DAG. All modes share the same executor self-loop; modes diverge on what happens **after** the executor finishes.

```
mode=baseline | mode=evolved
─────────────────────────────
  ┌──────────┐ done=False
  │ executor │◀────────┐
  └────┬─────┘         │
       │ done=True     │
       └──→ END        │
       (self-loop)─────┘

mode=evolve
───────────
  ┌──────────┐ done=False
  │ executor │◀────────────────────────────────┐
  └────┬─────┘                                 │
       │ done ∧ should_evaluate(state)         │
       ▼                                       │
  ┌──────────┐ should_synthesize=False         │
  │evaluator │──────────→ END                  │
  └────┬─────┘                                 │
       │ should_synthesize=True                │
       ▼                                       │
  ┌─────────────┐ synth wrote a file           │
  │ synthesizer │──────────→ verifier → END    │
  └────┬────────┘                              │
       │ skill name invalid / duplicate        │
       └──────────→ END                        │
```

**Conditional edges always pass an explicit mapping dict** (`{path_string: node_name}`). Otherwise LangGraph treats the routing function's return string as a literal node name and silently routes to a non-existent node. This is documented in `CLAUDE.md` because we burned ~30 minutes on it.

`recursion_limit=64` (vs LangGraph's default 25) — every executor self-loop spends one recursion slot, and 12 max steps × 1 pre-tool LLM round + 1 tool round = 24, exhausting the default before submit.

---

## 4. Executor (`src/mercury/nodes/executor.py`)

One LLM call per node invocation, then inline execution of any tool calls the model emitted, then a routing decision. Three exit conditions:

1. `submit` returned `passed=True` — sets `trace.success=True` and `done=True`.
2. `total_turns >= max_steps` (default 12).
3. Three consecutive turns produced no `tool_calls` (the model is talking instead of acting). Counter is reset to zero on any tool call.

The system prompt is templated with the manifest and `max_steps`. In `baseline` / `evolve` mode the manifest is empty; only `evolved` mode injects verified skills (and only their `(name, description)` pair — bodies are loaded on demand).

Tool dispatch: each tool's `result_str` is appended as a `ToolMessage`, but **`submit`'s result is also `json.loads`'d** to detect `passed=True`. This means tool implementations must serialise their return as a JSON string — a contract enforced by every wrapper in `tools.py`.

---

## 5. Tools (`src/mercury/tools.py`)

| Tool         | Purpose                                                                | Surface                                             |
| ------------ | ---------------------------------------------------------------------- | --------------------------------------------------- |
| `python_repl`| Execute Python in the sandbox                                          | `code: str → {exit_code, stdout, stderr, ...}`      |
| `read_file`  | Peek workspace file (UTF-8 text or hex preview)                        | `path, max_bytes=4096 → {content / content_hex, ...}` |
| `write_file` | Write UTF-8 to workspace (creates parent dirs)                         | `path, content → {ok, bytes}`                       |
| `load_skill` | Read full SKILL.md body (only callable in `evolved` mode meaningfully) | `name → {name, body} OR {error}`                    |
| `submit`     | Trigger the host-side `accept(workspace)` callable                     | `output_path, note → {passed, reason, output_path}` |

`build_tools(workspace, sandbox, skill_loader, on_submit) → ToolBundle` constructs all five and closes over per-run state. The bundle is passed into `make_executor_node`. **All tool outputs are truncated to 4 KB** before becoming `ToolMessage` content, otherwise long stderr from a Python failure can blow the context window.

`read_file` / `write_file` reject path traversal: they `resolve()` the joined path and verify the result is still under `workspace.resolve()`.

---

## 6. Evaluator (`src/mercury/nodes/evaluator.py`)

### Gate

```
should_evaluate(state):
    if not state.trace.success: return True            # always reflect on failures
    return state.trace.total_turns >= 4                # skip trivial successes
```

`MIN_TURNS_FOR_REFLECTION = 4` is a soft threshold — Day 5 evaluation showed Qwen-Plus solves most baseline tasks in 3 turns, so this skips the "no headroom" cases without burning tokens.

### Why `bind_tools`, not `with_structured_output`

The evaluator's output is a Pydantic schema (`ProposedSkillSchema`). The textbook way to get structured output is `llm.with_structured_output(schema, method="function_calling", strict=True)`. This **does not work** with Qwen because `tool_choice="required"` (which `with_structured_output` sets) conflicts with Qwen's thinking mode and crashes the call.

The workaround: bind a single-tool list (`[emit_skill_proposal]`) and read `response.tool_calls[0].args`. Plain-text content is also tried as a JSON fallback so a non-tool reply still has a recovery path. Both paths are unit-tested.

---

## 7. Synthesizer (`src/mercury/nodes/synthesizer.py`)

Pure I/O. Receives `proposed_skill` from the evaluator and writes the SKILL.md.

- **Name sanitisation**: lowercases, replaces whitespace / underscores with `-`, drops anything not in `[a-z0-9-]`, collapses runs of `-`. Garbage inputs like `"$$$"` fall back to the literal name `"skill"` rather than crashing.
- **Idempotence**: if `skills/library/<name>/SKILL.md` already exists, the synthesizer returns `None` and writes nothing. This means a re-run of the same task in evolve mode will not overwrite an existing skill (keeping rejected skills in `_rejected/` doesn't count — `_`-prefixed dirs are skipped).
- **Baseline metrics**: the trace's `total_tokens` / `total_turns` are written as `BaselineMetrics` in the frontmatter. These are the no-skill numbers (executor saw `manifest=[]` in evolve mode), and are what the verifier compares against later.

### SKILL.md frontmatter spec

```yaml
---
name: csv-mixed-line-endings           # kebab-case, ≤ 64 chars, dir name = name
description: When ... use this skill   # one sentence, shown in manifest
version: 1
applies_to: [csv]                       # task groups this skill targets
status: pending | verified | rejected   # only verified skills enter manifest
source_task: csv-005
baseline_metrics:
  tokens: 16269
  turns: 8
---

## When to use
...

## Steps
...

## Pitfalls
...
```

---

## 8. Verifier (`src/mercury/nodes/verifier.py`)

### Three-axis gate (`gate_decision`, pure function)

| Check                                          | Verdict if violated      |
| ---------------------------------------------- | ------------------------ |
| `source.success`                               | reject (skill broke it)  |
| `source.tokens > 0.85 × baseline_tokens`       | reject (token regression)|
| `source.turns > baseline_turns`                | reject (turn regression) |
| `neighbour is not None` ∧ `not neighbour.success` | reject (broke same-group) |
| `anti is not None` ∧ `anti.loaded_skill`       | reject (trigger too broad)|
| (else)                                         | **verified**             |

Source must satisfy *all three* axes (success ∧ tokens ≤ 0.85× ∧ turns ≤). Neighbour is checked for success only — we don't have cached baseline metrics for neighbours and re-running their full baselines would double the verifier's cost. Anti-trigger checks **whether the agent called `load_skill(<this skill>)`** on a cross-group task; the cross-group task itself isn't required to pass — we only care that the skill's `description` is specific enough not to fire on irrelevant inputs.

The **0.85× ratio** is documented in `CLAUDE.md` as load-bearing and not to be weakened without updating `ROADMAP.md`. It's calibrated for tasks where a skill saves ≥1 turn; on the simpler half of the task set it makes the gate structurally hard to pass (loading a skill costs +1 turn already, and the body adds ~500–1500 tokens to context). This is by design — false positives are more expensive than false negatives in a self-evolving system.

### Probe machinery (`run_task_with_manifest`)

For each of {source, neighbour, anti}, the verifier:

1. Prepares a fresh workspace from the task fixtures.
2. Spins up a brand-new `DockerSandbox` (no checkpointer — these runs are throwaway).
3. Compiles a one-shot graph (`executor → END`, no evolve nodes).
4. Invokes with a `manifest = [{name: skill_name, description: skill_desc}]` so the candidate is the *only* thing the agent sees.
5. Inspects the trace for any `load_skill(name=skill_name)` step to populate `RunMetrics.loaded_skill`.

The probe must use **`build_llm("executor")`** — `baseline_metrics` were captured under that model, so probing with a different one would make the 0.85× budget meaningless.

### Archive convention

On rejection, `archive_rejection(skill_dir, outcome=, rejected_root=)` moves the entire skill directory under `<library>/_rejected/<name>__<iso-ts>/` and writes a `rejection.json` containing the full `VerificationOutcome` — verdict, reason, and all three `RunMetrics`. The ISO timestamp's colons are replaced with `-` so the path is filesystem-safe on Windows.

`scan_manifest()` skips any directory whose name starts with `_` or `.`, so rejected skills never re-enter the manifest.

---

## 9. Sandbox (`src/mercury/sandbox/docker_sandbox.py`)

### Threat model

LLM-generated Python is hostile by assumption. The container exists to bound the blast radius of code that may, intentionally or not, exfiltrate data, escape the workspace, fork-bomb, or run for unbounded time.

### Container parameters

| Parameter            | Value                          | Threat countered                               |
| -------------------- | ------------------------------ | ---------------------------------------------- |
| `image`              | `mercury-sandbox:latest`       | We control the entire userland (no `pip install` at runtime — `network=none` would block it anyway). Built locally from `scripts/sandbox.Dockerfile`: `python:3.11-slim` + pandas / numpy / lxml / bs4 / chardet / regex / dateutil. |
| `command`            | `["sleep", "infinity"]`        | Container is long-lived; per-snippet code is delivered via `put_archive` + `exec_run`. One container per task ≈ 200× cheaper than one per snippet. |
| `network_mode`       | `none`                         | Outbound exfil + inbound RCE                  |
| `mem_limit`          | `512m`                         | Memory exhaustion / DoS                        |
| `nano_cpus`          | `1 × 10⁹` (1 CPU)              | CPU starvation                                 |
| `cap_drop`           | `ALL`                          | Privilege escalation via Linux capabilities    |
| `security_opt`       | `no-new-privileges:true`       | setuid escapes                                  |
| `pids_limit`         | `128`                          | Fork-bomb                                      |
| `working_dir`        | `/workspace`                   | Workspace is bind-mounted; relative paths resolve there |
| `volumes`            | `host_workspace:/workspace:rw` | Output files persist on host so `accept()` can read them |
| GNU `timeout` wrap   | `--signal=KILL <SANDBOX_TIMEOUT_SECONDS>` (default 30) | Per-snippet wallclock limit; exit 124/137 → `timed_out=True` |

`docker.from_env()` honours the user's Docker context, so this works with Docker Desktop on Windows / Mac and with native Docker on Linux. The Docker SDK's `dockerfile=` arg needs POSIX paths even on Windows — `Path.as_posix()` is used in `scripts/pull_docker_image.py`.

### Lifecycle

```python
with DockerSandbox(workspace) as sbx:
    # __enter__ → start() → containers.run(detach=True, ...)
    sbx.run("import pandas; ...")  # exec_run with timeout wrapper
    sbx.run("...")
# __exit__ → stop() → kill() + remove(force=True)
```

`stop()` always tries `kill()` then `remove(force=True)`, swallowing `APIError` / `NotFound` so a partial cleanup of a pre-existing zombie container doesn't crash the wrapper.

---

## 10. Skill loader (`src/mercury/skills/loader.py`)

Implements the **progressive-disclosure** half of the skills mechanism.

| Function                  | Purpose                                                            |
| ------------------------- | ------------------------------------------------------------------ |
| `parse_skill_file(path)`  | Split frontmatter and body, validate via `SkillFrontmatter`        |
| `write_skill_file(path, fm, body)` | Round-trip safe: `parse ∘ write = id`                       |
| `scan_manifest(library_dir, status="verified")` | List entries; default filters to verified; `_`-prefixed dirs skipped; malformed frontmatter is tolerated (skipped, doesn't crash) |
| `load_full(name)`         | Read full SKILL.md body for the `load_skill` tool                  |
| `manifest_to_dicts(...)`  | Reduce to `[{name, description}]` for the executor's system prompt |

Only `cli.py` (when mode=`evolved`) and `verifier.py` (when constructing the candidate's solo manifest) ever call `scan_manifest` / build a manifest. Everything else just sees what was passed via `AgentState.skill_manifest`.

---

## 11. Eval pipeline (`src/mercury/eval/`)

```
runner.run_one_task(task, mode, run_idx)
    → constructs sandbox + graph + initial state
    → invokes once
    → returns TaskResult dataclass

runner.run_bench(mode, task_ids?, progress_cb?)
    → iterates tasks sequentially (no parallelism — Docker startup
      contention + DashScope rate-limits make it lossy on small sets)
    → returns BenchResult { mode, timestamp, tasks: [TaskResult, ...] }

runner.save_bench(result)  → results/metrics_<mode>.json
runner.load_bench(path)    → BenchResult

metrics.compute(BenchResult)
    → BenchMetrics { n, pass_at_1, avg_tokens, avg_turns,
                     by_group: {group: GroupStats, ...} }

metrics.normalized_gain(p_before, p_after)
    → (p_after - p_before) / (1 - p_before)        if p_before < 1
    → 0.0                                          if p_before == 1   (clamp)

metrics.compare(baseline, evolved) → ComparisonMetrics
    { baseline, evolved, pass_delta, normalized_gain,
      tokens_ratio (= evolved/baseline; <1 = improvement),
      turns_ratio  (= evolved/baseline; <1 = improvement) }

plots.render_all(baseline, evolved, out_dir)
    → results/plots/{pass_at_1, tokens_per_task, tokens_radar}.png
```

`progress_cb(idx, total, task, result_or_None)` is invoked by `run_bench` once before each task and once after — used by the CLI to drive a per-task line of progress, and by tests to spy without printing.

`plot_tokens_radar` falls back to `plot_tokens_per_task` automatically when there are < 3 tasks (a polar plot with 1–2 axes is degenerate), so the same call site works on tiny benches.

---

## 12. Tasks (`src/mercury/eval/tasks/`)

```
<group>/<id>/
├── task.py     # TASK = register(Task(...)); accept(workspace) -> (bool, str)
├── input.*     # input file(s) — copied to workspace at run time
└── expected.*  # ground truth — STAYS ON HOST, never copied to workspace
```

The host / sandbox separation is a hard rule: the agent never sees `expected.*`. Acceptance is always a deterministic Python function comparing workspace output to expected. Doing this with an LLM-as-judge would create a feedback loop where the evaluator can score its own buggy reflections positively.

`_autodiscover()` walks subpackages on first call to `all_tasks()` / `get_task()` — task modules just register themselves at import time.

Current task set (16 tasks across 6 groups):

| group     | n | examples                                                              |
| --------- | - | --------------------------------------------------------------------- |
| `csv`     | 5 | BOM+;+, dirty whitespace, quoted numerics, UTF-16 LE, mixed line endings |
| `json`    | 2 | flat-array → CSV, nested flatten with dotted columns                  |
| `log`     | 2 | nginx combined-format, multi-line Python tracebacks                   |
| `multi`   | 2 | Cross-file JOIN with GBK encoding                                     |
| `pipeline`| 3 | Chained transformations + Z-score normalisation                        |
| `xml`     | 2 | XML → CSV (incl. broken / repair tasks)                                |

---

## 13. Models, env, prompt cache (`src/mercury/llm.py` / `config.py`)

`build_llm(role)` dispatches to one of three model identifiers:

| Role        | env override       | Default fallback        |
| ----------- | ------------------ | ----------------------- |
| `executor`  | `EXECUTOR_MODEL`   | `QWEN_PLUS_MODEL` ("qwen-plus") |
| `evaluator` | `EVALUATOR_MODEL`  | `QWEN_PLUS_MODEL`       |
| `flash`     | `FLASH_MODEL`      | `QWEN_FLASH_MODEL` ("qwen-flash") |

Temperatures are similarly per-role (`EXECUTOR_TEMPERATURE=0.0`, `EVALUATOR_TEMPERATURE=0.3`).

A **global LangChain prompt cache** is installed at import time:

```python
set_llm_cache(SQLiteCache(database_path=str(RESULTS_DIR / "prompt_cache.db")))
```

This means identical `(model, messages, params)` tuples are served from `results/prompt_cache.db` instead of re-billed to DashScope. Cached responses still go through tenacity's retry decorator (it just exits on the first try). To force a fresh run, delete the file or change any input — the verifier's per-probe `uuid` in `thread_id` is independent of cache key, so cache hits are content-addressed not identity-addressed.

`invoke_with_retry(llm, messages)` wraps `llm.invoke` with tenacity: 4 attempts, exponential backoff 2-20s. The underlying `ChatOpenAI` is constructed with `max_retries=0` so retry policy lives in one place.

---

## 14. Tests

| File                       | Type         | Needs Docker | Needs real LLM |
| -------------------------- | ------------ | ------------ | -------------- |
| `test_state.py` (3)        | pure         | no           | no             |
| `test_executor.py` (5)     | scripted LLM | no           | no             |
| `test_tasks.py` (~64)      | parametrised | no           | no             |
| `test_loader.py` (7)       | tmp_path I/O | no           | no             |
| `test_synthesizer.py` (8)  | tmp_path I/O | no           | no             |
| `test_evaluator.py` (~9)   | stub LLM     | no           | no             |
| `test_verifier.py` (22)    | stub runner  | no           | no             |
| `test_metrics.py` (9)      | pure         | no           | no             |
| `test_plots.py` (6)        | tmp_path PNG | no           | no             |
| `test_config.py` (6)       | env mocking  | no           | no             |
| `test_sandbox.py`          | integration  | **yes**      | no             |
| `test_tools_e2e.py`        | integration  | **yes**      | no             |
| `test_llm.py`              | API smoke    | no           | **yes**        |

Default invocation: `uv run pytest tests/` runs everything; CI without Docker / API key should skip the last three with `--ignore`.

The default count of **139 passing offline tests** corresponds to the first ten files. `test_sandbox.py` and `test_tools_e2e.py` add ~7 more if Docker is available.

---

## 15. Operational notes

- `mercury reset` wipes `skills/library/*` (preserving `.gitkeep`) and `results/state.db`. Use it before a fresh baseline run; it does **not** touch `results/prompt_cache.db` or `results/traces/` (those are deliberately survival).
- The LangGraph SqliteSaver is at `results/state.db`. The caller (CLI / runner) MUST `conn.close()` after `app.invoke` returns — `build_app` returns the connection in its tuple precisely so the caller can do that.
- Windows quirk: the CLI sets `sys.stdout.reconfigure("utf-8")` because the default GBK / cp936 mangles `rich`'s output and any non-ASCII task description.
- uv resolves Python 3.12.13 inside the `>=3.11,<3.13` range. That's expected — don't force 3.11 unless you have a reason.
- `langgraph-checkpoint-sqlite` is a separate package post-langgraph-0.2 — it must stay in `pyproject.toml` even though `langgraph` is also there.
