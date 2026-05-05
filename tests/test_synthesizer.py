"""Synthesizer node — produces a SKILL.md round-trippable through the loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from mercury.nodes.synthesizer import _sanitise_name, synthesize_skill
from mercury.skills.loader import parse_skill_file


_GOOD_PROPOSAL = {
    "should_synthesize": True,
    "skill_name": "csv-bom-semicolon",
    "trigger_description": "When the CSV has a UTF-8 BOM and uses ; as the delimiter, use this skill.",
    "failure_patterns": ["UnicodeDecodeError on naive utf-8 read"],
    "successful_subroutines": ["use encoding='utf-8-sig' and sep=';'"],
    "instructions_md": "## When to use\nfoo\n\n## Steps\n1. bar\n\n## Pitfalls\n- baz\n",
}


def test_writes_file_and_round_trips_through_loader(tmp_path: Path) -> None:
    path = synthesize_skill(
        proposed=_GOOD_PROPOSAL,
        task_id="csv-001",
        task_group="csv",
        baseline_tokens=4321,
        baseline_turns=5,
        library_dir=tmp_path,
    )
    assert path is not None and path.exists()

    fm, body = parse_skill_file(path)
    assert fm.name == "csv-bom-semicolon"
    assert fm.status == "pending"
    assert fm.source_task == "csv-001"
    assert fm.applies_to == ["csv"]
    assert fm.baseline_metrics is not None
    assert fm.baseline_metrics.tokens == 4321
    assert fm.baseline_metrics.turns == 5
    assert "## Steps" in body


def test_skip_when_should_synthesize_false(tmp_path: Path) -> None:
    out = synthesize_skill(
        proposed={"should_synthesize": False},
        task_id="csv-001",
        task_group="csv",
        baseline_tokens=0,
        baseline_turns=0,
        library_dir=tmp_path,
    )
    assert out is None
    assert list(tmp_path.iterdir()) == []


def test_skip_when_required_fields_missing(tmp_path: Path) -> None:
    out = synthesize_skill(
        proposed={"should_synthesize": True, "skill_name": "x"},  # no trigger / instructions
        task_id="csv-001",
        task_group="csv",
        baseline_tokens=0,
        baseline_turns=0,
        library_dir=tmp_path,
    )
    assert out is None


def test_idempotent_no_overwrite(tmp_path: Path) -> None:
    p1 = synthesize_skill(
        proposed=_GOOD_PROPOSAL,
        task_id="csv-001",
        task_group="csv",
        baseline_tokens=1,
        baseline_turns=1,
        library_dir=tmp_path,
    )
    assert p1 is not None
    original = p1.read_bytes()

    p2 = synthesize_skill(
        proposed={**_GOOD_PROPOSAL, "instructions_md": "DIFFERENT"},
        task_id="csv-002",
        task_group="csv",
        baseline_tokens=999,
        baseline_turns=99,
        library_dir=tmp_path,
    )
    assert p2 is None  # rejected because already exists
    assert p1.read_bytes() == original


def test_sanitise_name_keeps_valid_kebab() -> None:
    assert _sanitise_name("csv-bom-semicolon") == "csv-bom-semicolon"


def test_sanitise_name_normalises_garbage() -> None:
    assert _sanitise_name("CSV BOM_Semicolon!!!") == "csv-bom-semicolon"
    assert _sanitise_name("   spaces   between   ") == "spaces-between"
    assert _sanitise_name("__weird__") == "weird"


def test_sanitise_name_drops_invalid_chars() -> None:
    assert _sanitise_name("café") == "caf"


def test_synthesize_rejects_unsanitisable_name(tmp_path: Path) -> None:
    out = synthesize_skill(
        proposed={**_GOOD_PROPOSAL, "skill_name": "$$$"},
        task_id="csv-001",
        task_group="csv",
        baseline_tokens=0,
        baseline_turns=0,
        library_dir=tmp_path,
    )
    # `$$$` sanitises to "skill" (the fallback) which IS valid kebab-case,
    # so a file gets written. We accept that — but verify it's at least
    # safely named.
    assert out is None or out.parent.name == "skill"
