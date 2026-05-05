"""Skill loader / writer round-trip + manifest filtering."""

from __future__ import annotations

from pathlib import Path

import pytest

from mercury.skills.loader import (
    load_full,
    manifest_to_dicts,
    parse_skill_file,
    scan_manifest,
    write_skill_file,
)
from mercury.skills.schema import BaselineMetrics, SkillFrontmatter


def _make_skill(
    library: Path,
    name: str,
    *,
    status: str = "verified",
    description: str = "trigger description",
    body: str = "## When to use\nfoo\n\n## Steps\n1. bar\n",
) -> Path:
    fm = SkillFrontmatter(
        name=name,
        description=description,
        applies_to=["test"],
        status=status,  # type: ignore[arg-type]
        source_task="csv-001",
        baseline_metrics=BaselineMetrics(tokens=3000, turns=4),
    )
    path = library / name / "SKILL.md"
    write_skill_file(path, fm, body)
    return path


def test_write_then_parse_roundtrip(tmp_path: Path) -> None:
    path = _make_skill(tmp_path, "demo-skill")
    fm, body = parse_skill_file(path)
    assert fm.name == "demo-skill"
    assert fm.status == "verified"
    assert fm.baseline_metrics is not None
    assert fm.baseline_metrics.tokens == 3000
    assert "## Steps" in body


def test_scan_manifest_filters_by_status(tmp_path: Path) -> None:
    _make_skill(tmp_path, "good", status="verified")
    _make_skill(tmp_path, "bad", status="pending")
    _make_skill(tmp_path, "ugly", status="rejected")

    verified = scan_manifest(library_dir=tmp_path, status="verified")
    pending = scan_manifest(library_dir=tmp_path, status="pending")
    everything = scan_manifest(library_dir=tmp_path, status=None)

    assert {s.name for s in verified} == {"good"}
    assert {s.name for s in pending} == {"bad"}
    assert {s.name for s in everything} == {"good", "bad", "ugly"}


def test_scan_manifest_skips_underscore_dirs(tmp_path: Path) -> None:
    """`_rejected/` and similar housekeeping folders must be ignored."""
    _make_skill(tmp_path, "good")
    _make_skill(tmp_path, "_archive")
    manifest = scan_manifest(library_dir=tmp_path, status=None)
    assert {s.name for s in manifest} == {"good"}


def test_scan_manifest_tolerates_malformed_skill(tmp_path: Path) -> None:
    """A SKILL.md with broken YAML must NOT crash the scan."""
    _make_skill(tmp_path, "good")
    bad_dir = tmp_path / "broken"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("no frontmatter here", encoding="utf-8")
    manifest = scan_manifest(library_dir=tmp_path, status=None)
    assert {s.name for s in manifest} == {"good"}


def test_load_full_returns_body_and_name(tmp_path: Path) -> None:
    _make_skill(tmp_path, "demo-skill", body="## When to use\nthe thing\n")
    result = load_full("demo-skill", library_dir=tmp_path)
    assert result is not None
    assert result.name == "demo-skill"
    assert "the thing" in result.body


def test_load_full_returns_none_for_missing(tmp_path: Path) -> None:
    assert load_full("does-not-exist", library_dir=tmp_path) is None


def test_manifest_to_dicts_shape() -> None:
    fm = SkillFrontmatter(name="x", description="desc")
    [d] = manifest_to_dicts([fm])
    assert d == {"name": "x", "description": "desc"}
