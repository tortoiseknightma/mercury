"""Sandbox abstractions.

The agent never executes user-generated code in the host process — every
`python_repl` call is forwarded to a `SandboxBackend` implementation that
provides isolation, resource limits, and a clean filesystem.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: int
    timed_out: bool = False


class SandboxBackend(ABC):
    """Lifecycle:  start() -> run(code) * N  -> stop()."""

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def run(self, code: str, *, timeout: int | None = None) -> ExecResult: ...

    @abstractmethod
    def stop(self) -> None: ...

    def __enter__(self) -> "SandboxBackend":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()


from mercury.sandbox.docker_sandbox import DockerSandbox  # noqa: E402

__all__ = ["SandboxBackend", "ExecResult", "DockerSandbox"]
