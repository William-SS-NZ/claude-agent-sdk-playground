"""Tests for the rollback tool.

These exercise the tool directly (without going through MCP) by calling
the ``rollback`` coroutine. The tool validates paths against the real
repo layout, so we point its resolution roots at a tmp_path sandbox
using monkeypatch.
"""

import time
from pathlib import Path

import pytest

from agent_builder.tools import rollback as rollback_mod
from agent_builder.tools.rollback import rollback


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fake repo root with agent_builder/ and output/ subdirs.

    The rollback module resolves relative target_path against REPO_ROOT
    and validates the result is under one of REPO_ROOT / BUILDER_DIR /
    OUTPUT_DIR. Point all three at the sandbox.
    """
    (tmp_path / "agent_builder" / "identity").mkdir(parents=True)
    (tmp_path / "output" / "my-agent").mkdir(parents=True)

    monkeypatch.setattr(rollback_mod, "REPO_ROOT", tmp_path.resolve())
    monkeypatch.setattr(rollback_mod, "BUILDER_DIR", (tmp_path / "agent_builder").resolve())
    monkeypatch.setattr(rollback_mod, "OUTPUT_DIR", (tmp_path / "output").resolve())
    return tmp_path


def _write_backup(target: Path, stamp: str, content: str) -> Path:
    bak = target.with_suffix(target.suffix + f".bak-{stamp}")
    bak.write_text(content, encoding="utf-8")
    return bak


async def test_list_with_backups_returns_newest_first(sandbox: Path):
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("current", encoding="utf-8")
    _write_backup(target, "20260101-120000", "v1")
    _write_backup(target, "20260301-090000", "v2")
    _write_backup(target, "20260215-153045", "v1.5")

    result = await rollback({
        "action": "list",
        "target_path": "agent_builder/identity/AGENT.md",
    })

    assert "is_error" not in result
    text = result["content"][0]["text"]
    assert "Found 3 backup(s)" in text
    # Newest-first ordering: 2026-03-01 should appear before 2026-02-15 and 2026-01-01.
    march_idx = text.index("20260301-090000")
    feb_idx = text.index("20260215-153045")
    jan_idx = text.index("20260101-120000")
    assert march_idx < feb_idx < jan_idx
    # Size is reported.
    assert "bytes" in text


async def test_list_with_none_returns_clean_message(sandbox: Path):
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("no backups yet", encoding="utf-8")

    result = await rollback({
        "action": "list",
        "target_path": "agent_builder/identity/AGENT.md",
    })

    assert "is_error" not in result
    assert "no backups found" in result["content"][0]["text"].lower()


async def test_list_ignores_unrelated_bak_files(sandbox: Path):
    # Two different files, each with their own backups, in the same dir.
    target_a = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target_a.write_text("A", encoding="utf-8")
    target_b = sandbox / "agent_builder" / "identity" / "SOUL.md"
    target_b.write_text("B", encoding="utf-8")
    _write_backup(target_a, "20260101-120000", "A-old")
    _write_backup(target_b, "20260101-120000", "B-old")

    result = await rollback({
        "action": "list",
        "target_path": "agent_builder/identity/AGENT.md",
    })
    text = result["content"][0]["text"]
    assert "AGENT.md.bak-20260101-120000" in text
    assert "SOUL.md.bak-" not in text
    assert "Found 1 backup(s)" in text


async def test_restore_round_trips(sandbox: Path):
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("current", encoding="utf-8")
    bak = _write_backup(target, "20260101-120000", "original-v1")

    result = await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
        "backup_name": bak.name,
    })

    assert "is_error" not in result
    assert target.read_text(encoding="utf-8") == "original-v1"
    assert "Restored" in result["content"][0]["text"]


async def test_restore_writes_pre_restore_backup(sandbox: Path):
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("state-before-restore", encoding="utf-8")
    bak = _write_backup(target, "20260101-120000", "older-state")

    # Count existing backups (just the one we seeded).
    assert len(list(target.parent.glob("AGENT.md.bak-*"))) == 1

    result = await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
        "backup_name": bak.name,
    })
    assert "is_error" not in result

    # Now there should be a second backup whose contents match the target
    # *at the time of restore*, i.e. 'state-before-restore'.
    all_backups = list(target.parent.glob("AGENT.md.bak-*"))
    assert len(all_backups) == 2
    pre_restore = [b for b in all_backups if b.name != bak.name][0]
    assert pre_restore.read_text(encoding="utf-8") == "state-before-restore"
    assert "Pre-restore backup" in result["content"][0]["text"]


async def test_restore_is_itself_reversible(sandbox: Path):
    """After a restore, the pre-restore backup can be used to roll forward again."""
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("v2", encoding="utf-8")
    v1_bak = _write_backup(target, "20260101-120000", "v1")

    # Restore v1. Target becomes 'v1', a pre-restore backup of 'v2' is written.
    await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
        "backup_name": v1_bak.name,
    })
    assert target.read_text(encoding="utf-8") == "v1"

    # Find the pre-restore backup (the one not matching v1_bak).
    all_backups = list(target.parent.glob("AGENT.md.bak-*"))
    pre_restore = [b for b in all_backups if b.name != v1_bak.name][0]
    assert pre_restore.read_text(encoding="utf-8") == "v2"

    # Roll forward by restoring the pre-restore backup. Sleep >1s so the
    # new pre-restore stamp doesn't collide with the previous second.
    time.sleep(1.1)
    result = await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
        "backup_name": pre_restore.name,
    })
    assert "is_error" not in result
    assert target.read_text(encoding="utf-8") == "v2"


async def test_rejects_mismatched_backup_name(sandbox: Path):
    # Create two files in the same directory, each with its own backup.
    target_a = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target_a.write_text("A-current", encoding="utf-8")
    target_b = sandbox / "agent_builder" / "identity" / "SOUL.md"
    target_b.write_text("B-current", encoding="utf-8")
    b_bak = _write_backup(target_b, "20260101-120000", "B-old")

    # Try to restore SOUL.md.bak-... over AGENT.md. Must refuse.
    result = await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
        "backup_name": b_bak.name,
    })

    assert result.get("is_error") is True
    assert "does not belong to target" in result["content"][0]["text"]
    # And AGENT.md is untouched.
    assert target_a.read_text(encoding="utf-8") == "A-current"


async def test_rejects_path_traversal_in_target(sandbox: Path):
    # Create a file OUTSIDE the sandbox and try to reach it via ..
    outside = sandbox.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    result = await rollback({
        "action": "list",
        "target_path": "../secret.txt",
    })

    assert result.get("is_error") is True
    assert "escapes" in result["content"][0]["text"].lower()


async def test_rejects_absolute_target(sandbox: Path):
    result = await rollback({
        "action": "list",
        "target_path": "/etc/passwd",
    })
    assert result.get("is_error") is True
    assert "absolute" in result["content"][0]["text"].lower() or "relative" in result["content"][0]["text"].lower()


async def test_rejects_drive_letter_target(sandbox: Path):
    result = await rollback({
        "action": "list",
        "target_path": "C:/Windows/System32/evil.txt",
    })
    assert result.get("is_error") is True


async def test_rejects_path_traversal_in_backup_name(sandbox: Path):
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("current", encoding="utf-8")

    # Seed a backup in a sibling directory we should NOT be able to reach.
    other_dir = sandbox / "agent_builder"
    evil_bak = other_dir / "AGENT.md.bak-20260101-120000"
    evil_bak.write_text("traversal-payload", encoding="utf-8")

    # Attempt to traverse via backup_name.
    result = await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
        "backup_name": "../AGENT.md.bak-20260101-120000",
    })

    assert result.get("is_error") is True
    # Target is untouched.
    assert target.read_text(encoding="utf-8") == "current"


async def test_rejects_backup_name_with_slash(sandbox: Path):
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("current", encoding="utf-8")

    result = await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
        "backup_name": "subdir/AGENT.md.bak-20260101-120000",
    })
    assert result.get("is_error") is True


async def test_rejects_malformed_backup_name(sandbox: Path):
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("current", encoding="utf-8")

    result = await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
        "backup_name": "AGENT.md.bak-oops",
    })
    assert result.get("is_error") is True
    assert "does not match" in result["content"][0]["text"]


async def test_rejects_missing_backup_file(sandbox: Path):
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("current", encoding="utf-8")

    # Well-formed name but no file on disk.
    result = await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
        "backup_name": "AGENT.md.bak-20260101-120000",
    })
    assert result.get("is_error") is True
    assert "not found" in result["content"][0]["text"].lower()


async def test_rejects_unknown_action(sandbox: Path):
    result = await rollback({
        "action": "nuke",
        "target_path": "agent_builder/identity/AGENT.md",
    })
    assert result.get("is_error") is True


async def test_restore_requires_backup_name(sandbox: Path):
    target = sandbox / "agent_builder" / "identity" / "AGENT.md"
    target.write_text("current", encoding="utf-8")
    result = await rollback({
        "action": "restore",
        "target_path": "agent_builder/identity/AGENT.md",
    })
    assert result.get("is_error") is True
    assert "backup_name is required" in result["content"][0]["text"]


async def test_list_works_for_output_path(sandbox: Path):
    """Confirm the output/ root is reachable too, not just agent_builder/."""
    target = sandbox / "output" / "my-agent" / "tools.py"
    target.write_text("current", encoding="utf-8")
    _write_backup(target, "20260101-120000", "v1")

    result = await rollback({
        "action": "list",
        "target_path": "output/my-agent/tools.py",
    })
    assert "is_error" not in result
    assert "Found 1 backup(s)" in result["content"][0]["text"]
