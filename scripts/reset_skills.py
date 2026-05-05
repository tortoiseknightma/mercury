"""Wipe the skill library — keeps the directory + .gitkeep, removes all skills.

Use before a clean baseline run so the executor sees an empty manifest:
    uv run python scripts/reset_skills.py
"""

from __future__ import annotations

import shutil

from mercury.config import SKILL_LIBRARY_DIR


def main() -> None:
    if not SKILL_LIBRARY_DIR.exists():
        print(f"[reset_skills] library does not exist: {SKILL_LIBRARY_DIR}")
        return
    removed = 0
    for child in SKILL_LIBRARY_DIR.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1
    print(f"[reset_skills] removed {removed} entries from {SKILL_LIBRARY_DIR}")


if __name__ == "__main__":
    main()
