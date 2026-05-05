"""Docker-backed sandbox for executing untrusted Python snippets.

Design:
- One long-lived container per task. We use `exec_run` for each `python_repl`
  call, which is far cheaper than spawning a fresh container per snippet.
- Workspace is bind-mounted from the host so generated files persist after the
  container is torn down (the host's `submit()` reads them to run acceptance).
- Hard limits: memory, cpus, network=none, per-call timeout.
- The container runs as a non-root user-owned tmpfs path is unnecessary because
  we trust pandas et al not to fork-bomb; we still cap CPU and memory.

The interface matches `SandboxBackend`. A subprocess fallback can be added
later under the same protocol without touching call sites.
"""

from __future__ import annotations

import io
import shlex
import tarfile
import time
import uuid
from pathlib import Path
from typing import Optional

import docker
from docker.errors import APIError, ImageNotFound, NotFound
from docker.models.containers import Container

from mercury.config import load_config
from mercury.sandbox import ExecResult, SandboxBackend


CONTAINER_WORKSPACE = "/workspace"


class DockerSandbox(SandboxBackend):
    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        image: str | None = None,
        mem_limit: str | None = None,
        cpu_limit: float | None = None,
        timeout_seconds: int | None = None,
        name_prefix: str = "mercury-sbx",
    ) -> None:
        cfg = load_config().sandbox
        self.workspace_dir = Path(workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.image = image or cfg.image
        self.mem_limit = mem_limit or cfg.mem_limit
        self.cpu_limit = cpu_limit if cpu_limit is not None else cfg.cpu_limit
        self.default_timeout = timeout_seconds or cfg.timeout_seconds
        self.container_name = f"{name_prefix}-{uuid.uuid4().hex[:8]}"
        self._client: Optional[docker.DockerClient] = None
        self._container: Optional[Container] = None

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if self._container is not None:
            return
        self._client = docker.from_env()
        self._ensure_image()

        # nano_cpus = cpu_limit * 1e9
        nano_cpus = int(self.cpu_limit * 1_000_000_000)

        # Bind-mount the workspace.  We pin it as the cwd so the agent's
        # `python -c` calls resolve relative paths there.
        self._container = self._client.containers.run(
            image=self.image,
            name=self.container_name,
            command=["sleep", "infinity"],
            detach=True,
            remove=False,           # we remove explicitly in stop() to capture exit info
            network_mode="none",
            mem_limit=self.mem_limit,
            nano_cpus=nano_cpus,
            working_dir=CONTAINER_WORKSPACE,
            volumes={
                str(self.workspace_dir): {
                    "bind": CONTAINER_WORKSPACE,
                    "mode": "rw",
                },
            },
            # Best-effort hardening; some flags are no-ops on Windows backend.
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            pids_limit=128,
            tty=False,
            stdin_open=False,
        )

    def stop(self) -> None:
        if self._container is None:
            return
        try:
            self._container.kill()
        except (APIError, NotFound):
            pass
        try:
            self._container.remove(force=True)
        except (APIError, NotFound):
            pass
        self._container = None
        if self._client is not None:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------ exec

    def run(self, code: str, *, timeout: int | None = None) -> ExecResult:
        if self._container is None:
            raise RuntimeError("Sandbox not started; call start() or use as context manager")

        timeout = timeout or self.default_timeout

        # We write the snippet into the container as /tmp/snippet_<id>.py and
        # exec it with a timeout wrapper.  Quoting stdin in exec_run is finicky;
        # uploading via put_archive is robust for arbitrary code.
        snippet_name = f"snippet_{uuid.uuid4().hex[:8]}.py"
        snippet_host_path = f"/tmp/{snippet_name}"
        self._copy_into_container("/tmp", snippet_name, code.encode("utf-8"))

        cmd = ["timeout", "--signal=KILL", str(timeout), "python", snippet_host_path]

        start = time.perf_counter()
        try:
            result = self._container.exec_run(
                cmd=cmd,
                workdir=CONTAINER_WORKSPACE,
                demux=True,
                tty=False,
            )
        except APIError as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return ExecResult(
                stdout="",
                stderr=f"Docker API error: {e}",
                exit_code=-1,
                elapsed_ms=elapsed_ms,
            )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        stdout_bytes, stderr_bytes = result.output if isinstance(result.output, tuple) else (result.output, b"")
        stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
        stderr = (stderr_bytes or b"").decode("utf-8", errors="replace")

        # GNU `timeout` returns 124 on timeout (137 with --signal=KILL).
        timed_out = result.exit_code in (124, 137)

        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=result.exit_code if result.exit_code is not None else -1,
            elapsed_ms=elapsed_ms,
            timed_out=timed_out,
        )

    # ------------------------------------------------------------------ helpers

    def _ensure_image(self) -> None:
        assert self._client is not None
        try:
            self._client.images.get(self.image)
        except ImageNotFound:
            # Pulling here is convenient but slow on first run.  Prefer running
            # `scripts/pull_docker_image.py` ahead of time.
            self._client.images.pull(self.image)

    def _copy_into_container(self, dest_dir: str, filename: str, data: bytes) -> None:
        """Inject a single in-memory file into the running container."""
        assert self._container is not None
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w") as tf:
            info = tarfile.TarInfo(name=filename)
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
        tar_buf.seek(0)
        self._container.put_archive(path=dest_dir, data=tar_buf.getvalue())


def make_sandbox(workspace_dir: str | Path) -> DockerSandbox:
    """Convenience constructor used by tools.py / executor."""
    return DockerSandbox(workspace_dir)
