"""Per-role model dispatch — env precedence + build_llm picks the right model.

These tests don't make real LLM calls — they just inspect the `model_name`
attribute on the returned ChatOpenAI to confirm config wiring.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop `load_config()` from re-reading the developer's .env file mid-test.

    Without this, dotenv would silently re-inject values like `QWEN_PLUS_MODEL`
    after a `monkeypatch.delenv`, breaking the precedence assertions.
    `load_config` reads `os.environ` at call time so we don't need to reload
    the module — patching the symbol it imported once is enough.
    """
    monkeypatch.setattr("mercury.config.load_dotenv", lambda *a, **kw: False)


def test_default_roles_fall_back_to_qwen_plus(monkeypatch: pytest.MonkeyPatch) -> None:
    """No per-role override + no QWEN_PLUS_MODEL → built-in default 'qwen-plus'."""
    for v in ("EXECUTOR_MODEL", "EVALUATOR_MODEL", "FLASH_MODEL", "QWEN_PLUS_MODEL", "QWEN_FLASH_MODEL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-key")
    from mercury.config import load_config

    cfg = load_config()
    assert cfg.llm.executor_model == "qwen-plus"
    assert cfg.llm.evaluator_model == "qwen-plus"
    assert cfg.llm.flash_model == "qwen-flash"


def test_qwen_plus_fallback_propagates_to_executor_and_evaluator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting QWEN_PLUS_MODEL changes both executor and evaluator defaults."""
    monkeypatch.setenv("QWEN_PLUS_MODEL", "qwen3.6-plus")
    monkeypatch.delenv("EXECUTOR_MODEL", raising=False)
    monkeypatch.delenv("EVALUATOR_MODEL", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-key")
    from mercury.config import load_config

    cfg = load_config()
    assert cfg.llm.executor_model == "qwen3.6-plus"
    assert cfg.llm.evaluator_model == "qwen3.6-plus"


def test_executor_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """EXECUTOR_MODEL overrides per-role; EVALUATOR_MODEL stays at its own fallback."""
    monkeypatch.setenv("QWEN_PLUS_MODEL", "qwen-plus")
    monkeypatch.setenv("EXECUTOR_MODEL", "qwen-flash")
    monkeypatch.delenv("EVALUATOR_MODEL", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-key")
    from mercury.config import load_config

    cfg = load_config()
    assert cfg.llm.executor_model == "qwen-flash"
    assert cfg.llm.evaluator_model == "qwen-plus"


def test_build_llm_dispatches_to_role_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_llm('executor') returns a ChatOpenAI bound to executor_model."""
    monkeypatch.setenv("QWEN_PLUS_MODEL", "qwen-plus")
    monkeypatch.setenv("EXECUTOR_MODEL", "qwen-flash")
    monkeypatch.setenv("EVALUATOR_MODEL", "qwen-max")
    monkeypatch.setenv("FLASH_MODEL", "qwen-turbo")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-key")
    from mercury.llm import build_llm

    assert build_llm("executor").model_name == "qwen-flash"
    assert build_llm("evaluator").model_name == "qwen-max"
    assert build_llm("flash").model_name == "qwen-turbo"


def test_build_llm_unknown_role_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-key")
    from mercury.llm import build_llm

    with pytest.raises(ValueError, match="unknown role"):
        build_llm("synthesizer")  # type: ignore[arg-type]


def test_build_llm_role_temperatures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each role uses its own temperature env when no override is passed."""
    monkeypatch.setenv("EXECUTOR_TEMPERATURE", "0.1")
    monkeypatch.setenv("EVALUATOR_TEMPERATURE", "0.7")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-key")
    from mercury.llm import build_llm

    assert build_llm("executor").temperature == pytest.approx(0.1)
    assert build_llm("evaluator").temperature == pytest.approx(0.7)
    # Caller can still override at call time.
    assert build_llm("executor", temperature=0.5).temperature == pytest.approx(0.5)
