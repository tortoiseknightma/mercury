"""End-to-end smoke: real sandbox + workspace + tools, no LLM in the loop.

This test exercises the full Day-1 stack from the executor's perspective minus
the LLM call: prepare workspace -> start sandbox -> python_repl reads/writes
files -> submit triggers acceptance check.
"""

from __future__ import annotations

import json

import pytest


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not available")


def test_csv_001_full_stack_via_tools() -> None:
    from mercury.eval.tasks import get_task
    from mercury.sandbox import DockerSandbox
    from mercury.tools import build_tools
    from mercury.workspace import prepare

    task = get_task("csv-001")
    workspace = prepare(task, run_label="e2e_smoke")

    submitted = {}

    def on_submit(output_path: str, note: str) -> dict:
        passed, reason = task.accept(workspace)
        submitted["passed"] = passed
        submitted["reason"] = reason
        return {"passed": passed, "reason": reason, "output_path": output_path}

    with DockerSandbox(workspace) as sbx:
        tools = build_tools(
            workspace=workspace,
            sandbox=sbx,
            skill_loader=lambda name: None,
            on_submit=on_submit,
        )

        # Hard-coded "perfect" solution to verify the rails — not what the agent does.
        solver = (
            "import pandas as pd\n"
            "df = pd.read_csv('input.csv', sep=';', encoding='utf-8-sig', decimal=',')\n"
            "df.to_csv('output.csv', index=False)\n"
            "print('rows:', len(df), 'cols:', list(df.columns))\n"
        )
        repl_out = json.loads(tools.python_repl.invoke({"code": solver}))
        assert repl_out["exit_code"] == 0, repl_out
        assert "rows:" in repl_out["stdout"]

        sub_out = json.loads(tools.submit.invoke({"output_path": "output.csv", "note": ""}))
        assert sub_out["passed"] is True, sub_out

    assert submitted == {"passed": True, "reason": "ok"}
