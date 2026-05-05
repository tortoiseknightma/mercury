"""Tools exposed to the executor.

These are *thin* wrappers — the heavy lifting lives in the sandbox / skill
loader. Each wrapper returns a string (LangChain serializes ToolMessages as
strings), and the executor node handles trace bookkeeping in the graph layer.

Tools are constructed per-run via `build_tools(workspace, sandbox, ...)` so
they can close over task-specific state (workspace path, sandbox handle, skill
loader, submit hook) without leaking globals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from mercury.sandbox import SandboxBackend


MAX_OUTPUT_BYTES = 4096


def _truncate(s: str, n: int = MAX_OUTPUT_BYTES) -> str:
    if len(s.encode("utf-8")) <= n:
        return s
    enc = s.encode("utf-8")[:n]
    # Avoid splitting a multi-byte char.
    safe = enc.decode("utf-8", errors="ignore")
    return safe + f"\n…[truncated; {len(s.encode('utf-8'))-n} bytes hidden]"


# ----------------------------------------------------------------------- python_repl


class PythonReplArgs(BaseModel):
    code: str = Field(description="Python source to execute in the sandboxed container.")


def make_python_repl(sandbox: SandboxBackend) -> StructuredTool:
    def _run(code: str) -> str:
        result = sandbox.run(code)
        payload = {
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "elapsed_ms": result.elapsed_ms,
            "stdout": _truncate(result.stdout),
            "stderr": _truncate(result.stderr),
        }
        return json.dumps(payload, ensure_ascii=False)

    return StructuredTool.from_function(
        func=_run,
        name="python_repl",
        description=(
            "Execute Python code inside an isolated Linux container "
            "(network=none, mem<=512m, cpu<=1, 30s timeout). "
            "The current working directory is /workspace; relative paths resolve there. "
            "Returns a JSON object with stdout/stderr/exit_code. "
            "Stateless across calls — re-import modules and re-open files each time."
        ),
        args_schema=PythonReplArgs,
    )


# ----------------------------------------------------------------------- read_file


class ReadFileArgs(BaseModel):
    path: str = Field(description="Path relative to the workspace root.")
    max_bytes: int = Field(default=4096, description="Truncate after this many bytes.")


def make_read_file(workspace: Path) -> StructuredTool:
    def _run(path: str, max_bytes: int = 4096) -> str:
        full = (workspace / path).resolve()
        if not str(full).startswith(str(workspace.resolve())):
            return json.dumps({"error": "path escapes workspace"})
        if not full.exists():
            return json.dumps({"error": f"file not found: {path}"})
        raw = full.read_bytes()[:max_bytes]
        try:
            text = raw.decode("utf-8")
            return json.dumps({"content": text, "encoding": "utf-8", "bytes": len(raw)})
        except UnicodeDecodeError:
            return json.dumps(
                {
                    "content_hex": raw[:256].hex(),
                    "encoding": "binary",
                    "bytes": len(raw),
                    "note": "Not valid UTF-8 — use python_repl with appropriate encoding.",
                }
            )

    return StructuredTool.from_function(
        func=_run,
        name="read_file",
        description=(
            "Read a file from the workspace and return its content (or hex preview if non-UTF-8). "
            "Use this for quick peeks; for parsing use python_repl."
        ),
        args_schema=ReadFileArgs,
    )


# ----------------------------------------------------------------------- write_file


class WriteFileArgs(BaseModel):
    path: str = Field(description="Path relative to workspace root.")
    content: str = Field(description="UTF-8 text to write.")


def make_write_file(workspace: Path) -> StructuredTool:
    def _run(path: str, content: str) -> str:
        full = (workspace / path).resolve()
        if not str(full).startswith(str(workspace.resolve())):
            return json.dumps({"error": "path escapes workspace"})
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return json.dumps({"ok": True, "bytes": len(content.encode("utf-8"))})

    return StructuredTool.from_function(
        func=_run,
        name="write_file",
        description=(
            "Write UTF-8 text to a workspace file. Creates parent directories. "
            "Prefer python_repl for binary or large outputs."
        ),
        args_schema=WriteFileArgs,
    )


# ----------------------------------------------------------------------- load_skill


class LoadSkillArgs(BaseModel):
    name: str = Field(description="The skill's `name` field as listed in the manifest.")


@dataclass
class SkillLoadResult:
    name: str
    body: str


def make_load_skill(loader: Callable[[str], Optional[SkillLoadResult]]) -> StructuredTool:
    def _run(name: str) -> str:
        result = loader(name)
        if result is None:
            return json.dumps({"error": f"skill not found: {name}"})
        return json.dumps({"name": result.name, "body": result.body})

    return StructuredTool.from_function(
        func=_run,
        name="load_skill",
        description=(
            "Load the full instructions of a previously verified skill. "
            "Call this when the manifest description matches the current task."
        ),
        args_schema=LoadSkillArgs,
    )


# ----------------------------------------------------------------------- submit


class SubmitArgs(BaseModel):
    output_path: str = Field(
        default="output.csv",
        description="Path to the final answer file (relative to workspace).",
    )
    note: str = Field(default="", description="Free-text rationale (optional).")


def make_submit(on_submit: Callable[[str, str], dict]) -> StructuredTool:
    def _run(output_path: str = "output.csv", note: str = "") -> str:
        return json.dumps(on_submit(output_path, note))

    return StructuredTool.from_function(
        func=_run,
        name="submit",
        description=(
            "Declare the task complete. Triggers the deterministic acceptance check. "
            "Returns a JSON object with `passed` (bool) and `reason` (str). "
            "If `passed=false`, you MAY continue iterating and call submit again."
        ),
        args_schema=SubmitArgs,
    )


# ----------------------------------------------------------------------- bundle


@dataclass
class ToolBundle:
    python_repl: StructuredTool
    read_file: StructuredTool
    write_file: StructuredTool
    load_skill: StructuredTool
    submit: StructuredTool

    def as_list(self) -> list[StructuredTool]:
        return [self.python_repl, self.read_file, self.write_file, self.load_skill, self.submit]


def build_tools(
    *,
    workspace: Path,
    sandbox: SandboxBackend,
    skill_loader: Callable[[str], Optional[SkillLoadResult]],
    on_submit: Callable[[str, str], dict],
) -> ToolBundle:
    return ToolBundle(
        python_repl=make_python_repl(sandbox),
        read_file=make_read_file(workspace),
        write_file=make_write_file(workspace),
        load_skill=make_load_skill(skill_loader),
        submit=make_submit(on_submit),
    )
