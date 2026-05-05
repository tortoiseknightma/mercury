"""LLM factory for DashScope-hosted Qwen models via the OpenAI-compatible API.

`build_llm(role)` dispatches to the model assigned to that role in
`LLMConfig` (set via env vars — see `.env.example`). Roles:

  - "executor" — used by the agent loop AND by the verifier's probe runs
    (the latter MUST match the former so verification metrics stay
    comparable to the recorded baseline)
  - "evaluator" — used by the trace-reflection node
  - "flash" — light model reserved for the Day 6 pre-screen

Each role has a default temperature; callers can override via `temperature=`.
The actual model identifier is whatever the user put in `EXECUTOR_MODEL` /
`EVALUATOR_MODEL` / `FLASH_MODEL` (each falling back to `QWEN_PLUS_MODEL` or
`QWEN_FLASH_MODEL` respectively).
"""

from __future__ import annotations

from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.globals import set_llm_cache
from langchain_community.cache import SQLiteCache
from tenacity import retry, stop_after_attempt, wait_exponential

from mercury.config import load_config, RESULTS_DIR

# Set up global prompt cache
_db_path = RESULTS_DIR / "prompt_cache.db"
_db_path.parent.mkdir(parents=True, exist_ok=True)
set_llm_cache(SQLiteCache(database_path=str(_db_path)))


Role = Literal["executor", "evaluator", "flash"]


def build_llm(
    role: Role = "executor",
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """Construct a Qwen chat model for `role`.

    DashScope's OpenAI-compat endpoint accepts standard `chat.completions` and
    `tool_calls` schemas, so no Qwen-specific knobs need to leak here. We also
    set `max_retries=0` and wrap the call ourselves with tenacity (see
    `invoke_with_retry`) so the backoff policy is centralised.
    """
    cfg = load_config()
    if role == "executor":
        model = cfg.llm.executor_model
        default_temp = cfg.llm.executor_temperature
    elif role == "evaluator":
        model = cfg.llm.evaluator_model
        default_temp = cfg.llm.evaluator_temperature
    elif role == "flash":
        model = cfg.llm.flash_model
        default_temp = 0.0
    else:
        raise ValueError(f"unknown role: {role!r}")

    return ChatOpenAI(
        model=model,
        api_key=cfg.llm.api_key,
        base_url=cfg.llm.base_url,
        temperature=temperature if temperature is not None else default_temp,
        max_tokens=max_tokens,
        timeout=120,
        max_retries=0,
    )


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    reraise=True,
)
def invoke_with_retry(llm: ChatOpenAI, messages):
    """Wrap llm.invoke with exponential backoff for transient API errors."""
    return llm.invoke(messages)
