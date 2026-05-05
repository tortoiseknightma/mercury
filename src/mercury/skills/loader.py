"""Skill library loader — implements progressive disclosure.

At agent startup we scan `skills/library/<name>/SKILL.md` for every skill
whose frontmatter says `status: verified`, and inject just (name, description)
pairs into the system prompt. The full markdown body is loaded on-demand by
the `load_skill` tool, so the executor's first-turn context stays small.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from mercury.config import SKILL_LIBRARY_DIR
from mercury.skills.schema import SkillFrontmatter, SkillStatus
from mercury.tools import SkillLoadResult


SKILL_FILENAME = "SKILL.md"


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a SKILL.md into (frontmatter_dict, markdown_body)."""
    if not text.startswith("---"):
        raise ValueError("SKILL.md must start with a YAML frontmatter block")
    # Find the closing fence on its own line.
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        raise ValueError("SKILL.md frontmatter block is not closed")
    fm_text = rest[:end]
    body = rest[end + 4 :].lstrip("\n")
    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        raise ValueError(f"frontmatter is not a YAML mapping (got {type(fm).__name__})")
    return fm, body


def parse_skill_file(path: Path) -> tuple[SkillFrontmatter, str]:
    text = path.read_text(encoding="utf-8")
    fm_dict, body = _split_frontmatter(text)
    try:
        frontmatter = SkillFrontmatter(**fm_dict)
    except ValidationError as e:
        raise ValueError(f"invalid frontmatter at {path}: {e}") from e
    return frontmatter, body


def write_skill_file(
    path: Path,
    frontmatter: SkillFrontmatter,
    body: str,
) -> None:
    """Round-trip-safe writer (parse_skill_file ∘ write_skill_file = id)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_dict = frontmatter.model_dump(exclude_none=True)
    yaml_block = yaml.dump(fm_dict, sort_keys=False, allow_unicode=True)
    body_clean = body.rstrip("\n")
    path.write_text(f"---\n{yaml_block}---\n\n{body_clean}\n", encoding="utf-8")


def scan_manifest(
    *,
    library_dir: Path | None = None,
    status: Optional[SkillStatus] = "verified",
) -> list[SkillFrontmatter]:
    """List skills, optionally filtered by status.

    Args:
        library_dir: override for tests; defaults to the project library.
        status: filter; pass None to list everything.
    """
    base = library_dir or SKILL_LIBRARY_DIR
    out: list[SkillFrontmatter] = []
    if not base.exists():
        return out
    for skill_dir in sorted(base.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith(("_", ".")):
            continue
        skill_md = skill_dir / SKILL_FILENAME
        if not skill_md.exists():
            continue
        try:
            fm, _ = parse_skill_file(skill_md)
        except ValueError:
            # Malformed skills don't crash the agent — they just don't show up.
            continue
        if status is not None and fm.status != status:
            continue
        out.append(fm)
    return out


def load_full(
    name: str,
    *,
    library_dir: Path | None = None,
) -> Optional[SkillLoadResult]:
    """Read the full SKILL.md body for a skill (the `load_skill` tool calls this)."""
    base = library_dir or SKILL_LIBRARY_DIR
    skill_md = base / name / SKILL_FILENAME
    if not skill_md.exists():
        return None
    try:
        fm, body = parse_skill_file(skill_md)
    except ValueError:
        return None
    return SkillLoadResult(name=fm.name, body=body)


def manifest_to_dicts(manifest: list[SkillFrontmatter]) -> list[dict[str, str]]:
    """Reduce manifest entries to the (name, description) pairs the executor's
    system prompt needs."""
    return [{"name": s.name, "description": s.description} for s in manifest]
