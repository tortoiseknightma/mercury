"""Centralized configuration: env vars, paths, hyperparameters."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "results"
TRACES_DIR = RESULTS_DIR / "traces"
PLOTS_DIR = RESULTS_DIR / "plots"
SKILL_LIBRARY_DIR = Path(__file__).resolve().parent / "skills" / "library"
SKILL_REJECTED_DIR = SKILL_LIBRARY_DIR / "_rejected"
EVAL_TASKS_DIR = Path(__file__).resolve().parent / "eval" / "tasks"


def _ensure_dirs() -> None:
    for d in (RESULTS_DIR, TRACES_DIR, PLOTS_DIR, SKILL_LIBRARY_DIR, SKILL_REJECTED_DIR):
        d.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    # Per-role model assignments. Each defaults to `QWEN_PLUS_MODEL` if its
    # specific env var is unset. The verifier deliberately reuses
    # `executor_model` for its probe runs — baseline metrics were measured with
    # the executor's model, so verification has to be on the same footing.
    executor_model: str
    evaluator_model: str
    flash_model: str  # reserved for Day 6 flash pre-screen; not yet wired
    executor_temperature: float
    evaluator_temperature: float


@dataclass(frozen=True)
class SandboxConfig:
    image: str
    mem_limit: str
    cpu_limit: float
    timeout_seconds: int


@dataclass(frozen=True)
class HarnessConfig:
    max_steps: int


@dataclass(frozen=True)
class Config:
    llm: LLMConfig
    sandbox: SandboxConfig
    harness: HarnessConfig
    project_root: Path = field(default=PROJECT_ROOT)


def load_config() -> Config:
    """Load configuration from .env (idempotent)."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    _ensure_dirs()

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        # Defer hard failure to first LLM call so tests / sandbox-only paths still import.
        api_key = "MISSING_DASHSCOPE_API_KEY"

    # `QWEN_PLUS_MODEL` / `QWEN_FLASH_MODEL` are kept as the *fallback* model
    # identifiers; the per-role overrides take precedence when set. This
    # lets a user point the executor at a weaker model (e.g.
    # `EXECUTOR_MODEL=qwen-flash`) so traces are long enough for the
    # evaluator to find a reusable pattern, while keeping the evaluator on a
    # smarter model for reflection.
    plus_default = os.environ.get("QWEN_PLUS_MODEL", "qwen-plus")
    flash_default = os.environ.get("QWEN_FLASH_MODEL", "qwen-flash")

    return Config(
        llm=LLMConfig(
            api_key=api_key,
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            executor_model=os.environ.get("EXECUTOR_MODEL", plus_default),
            evaluator_model=os.environ.get("EVALUATOR_MODEL", plus_default),
            flash_model=os.environ.get("FLASH_MODEL", flash_default),
            executor_temperature=float(os.environ.get("EXECUTOR_TEMPERATURE", "0.0")),
            evaluator_temperature=float(os.environ.get("EVALUATOR_TEMPERATURE", "0.3")),
        ),
        sandbox=SandboxConfig(
            image=os.environ.get("SANDBOX_IMAGE", "mercury-sandbox:latest"),
            mem_limit=os.environ.get("SANDBOX_MEM_LIMIT", "512m"),
            cpu_limit=float(os.environ.get("SANDBOX_CPU_LIMIT", "1.0")),
            timeout_seconds=int(os.environ.get("SANDBOX_TIMEOUT_SECONDS", "30")),
        ),
        harness=HarnessConfig(
            max_steps=int(os.environ.get("MAX_STEPS", "12")),
        ),
    )
