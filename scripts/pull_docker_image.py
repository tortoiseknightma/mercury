"""Build the local sandbox image (mercury-sandbox:latest).

The image is python:3.11-slim with pandas / numpy / lxml etc. pre-installed,
because the running container has `network=none` and cannot pip install.

Run this once before the first `mercury run`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import docker
from docker.errors import APIError, BuildError, DockerException

from mercury.config import PROJECT_ROOT, load_config


def main() -> int:
    cfg = load_config().sandbox
    print(f"Building image '{cfg.image}' ...")
    try:
        client = docker.from_env()
    except DockerException as e:
        print(f"Failed to connect to Docker daemon: {e}", file=sys.stderr)
        print("Hint: start Docker Desktop and rerun.", file=sys.stderr)
        return 2

    dockerfile = PROJECT_ROOT / "scripts" / "sandbox.Dockerfile"
    if not dockerfile.exists():
        print(f"Dockerfile not found: {dockerfile}", file=sys.stderr)
        return 2

    try:
        # First pull the base image so build doesn't stall on it.
        print("  pulling base python:3.11-slim ...")
        for _ in client.api.pull("python:3.11-slim", stream=True, decode=True):
            pass

        print("  building ...")
        # Docker daemon expects POSIX-style relative path even on Windows.
        rel = dockerfile.relative_to(PROJECT_ROOT).as_posix()
        _, log_stream = client.images.build(
            path=str(PROJECT_ROOT),
            dockerfile=rel,
            tag=cfg.image,
            rm=True,
        )
        for chunk in log_stream:
            line = chunk.get("stream") or chunk.get("status") or ""
            line = line.rstrip()
            if line:
                print(f"  {line}")
    except BuildError as e:
        print(f"Build failed: {e}", file=sys.stderr)
        for log in e.build_log:
            if "stream" in log:
                print(log["stream"], end="", file=sys.stderr)
        return 1
    except APIError as e:
        print(f"Docker API error: {e}", file=sys.stderr)
        return 1

    print(f"Done. Image cached: {cfg.image}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
