"""Smoke tests for the Docker sandbox.

Skipped automatically when the Docker daemon isn't reachable.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest


def _docker_available() -> bool:
    try:
        import docker  # noqa: F401

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker daemon not available; start Docker Desktop to run sandbox tests.",
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "ws"


def test_run_simple_arithmetic(workspace: Path) -> None:
    from mercury.sandbox import DockerSandbox

    with DockerSandbox(workspace) as sbx:
        result = sbx.run("print(2 + 2)")
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == "4"
    assert not result.timed_out


def test_workspace_is_writable(workspace: Path) -> None:
    from mercury.sandbox import DockerSandbox

    with DockerSandbox(workspace) as sbx:
        sbx.run("open('hello.txt', 'w').write('mercury')")
    assert (workspace / "hello.txt").read_text() == "mercury"


def test_no_network(workspace: Path) -> None:
    from mercury.sandbox import DockerSandbox

    code = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://example.com', timeout=2)\n"
        "    print('NETWORK_OPEN')\n"
        "except Exception as e:\n"
        "    print('NETWORK_BLOCKED:', type(e).__name__)\n"
    )
    with DockerSandbox(workspace) as sbx:
        result = sbx.run(code)
    assert "NETWORK_BLOCKED" in result.stdout, result.stdout


def test_timeout_kills_runaway_loop(workspace: Path) -> None:
    from mercury.sandbox import DockerSandbox

    with DockerSandbox(workspace, timeout_seconds=2) as sbx:
        result = sbx.run("while True: pass")
    assert result.timed_out
