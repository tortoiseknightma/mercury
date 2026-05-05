"""Quick smoke: prints the model id chosen for each role."""
from __future__ import annotations

from mercury.config import load_config
from mercury.llm import build_llm


def main() -> None:
    cfg = load_config()
    print(f"executor_model = {cfg.llm.executor_model}")
    print(f"evaluator_model = {cfg.llm.evaluator_model}")
    print(f"flash_model = {cfg.llm.flash_model}")
    print(f"build_llm('executor').model_name  = {build_llm('executor').model_name}")
    print(f"build_llm('evaluator').model_name = {build_llm('evaluator').model_name}")
    print(f"build_llm('flash').model_name     = {build_llm('flash').model_name}")


if __name__ == "__main__":
    main()
