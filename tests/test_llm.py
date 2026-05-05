"""LLM smoke tests — DashScope OpenAI-compat endpoint.

Skipped when DASHSCOPE_API_KEY is unset, so CI / dev without secrets is fine.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from mercury.config import PROJECT_ROOT


# Load .env before the skip predicate evaluates.
load_dotenv(PROJECT_ROOT / ".env", override=False)


pytestmark = pytest.mark.skipif(
    not os.environ.get("DASHSCOPE_API_KEY"),
    reason="DASHSCOPE_API_KEY not set; skipping live LLM tests.",
)


def test_executor_responds_to_simple_prompt() -> None:
    from mercury.llm import build_llm

    llm = build_llm("executor", temperature=0.0, max_tokens=32)
    msg = llm.invoke("Reply with the single word: pong")
    assert "pong" in msg.content.lower()


def test_executor_can_call_a_tool() -> None:
    """Verifies tool calling propagates through langchain-openai → DashScope."""
    from langchain_core.tools import tool

    from mercury.llm import build_llm

    @tool
    def add(a: int, b: int) -> int:
        """Return a + b."""
        return a + b

    llm = build_llm("executor", temperature=0.0).bind_tools([add])
    response = llm.invoke("What is 3 + 4? Use the add tool.")
    assert response.tool_calls, f"expected a tool call, got: {response.content!r}"
    call = response.tool_calls[0]
    assert call["name"] == "add"
    assert call["args"] == {"a": 3, "b": 4}


def test_flash_responds() -> None:
    from mercury.llm import build_llm

    llm = build_llm("flash", temperature=0.0, max_tokens=16)
    msg = llm.invoke("Reply with: ok")
    assert msg.content.strip().lower().startswith("ok")
