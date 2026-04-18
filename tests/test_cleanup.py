"""Tests for agent_builder.cleanup.sweep_artifacts."""

import os
import time
from pathlib import Path

from agent_builder.cleanup import sweep_artifacts


def _make_old(path: Path, days_old: int) -> None:
    """Set mtime to `days_old` days in the past."""
    past = time.time() - (days_old * 86400) - 60  # +60s so it's strictly older
    os.utime(path, (past, past))


def _seed_repo(root: Path) -> None:
    """Create the dirs sweep_artifacts expects."""
    (root / "agent_builder").mkdir()
    (root / "agent_builder" / "logs").mkdir()
    (root / "output").mkdir()


def test_sweep_with_no_artifacts_returns_empty_summary(tmp_path: Path):
    _seed_repo(tmp_path)
    summary = sweep_artifacts(tmp_path, older_than_days=7, dry_run=True)
    assert summary["bak_files"] == []
    assert summary["builder_logs"] == []
    assert summary["screenshots"] is None
    assert summary["bytes"] == 0


def test_sweep_finds_bak_files_in_agent_builder_and_output(tmp_path: Path):
    _seed_repo(tmp_path)
    bak1 = tmp_path / "agent_builder" / "identity" / "AGENT.md.bak-20250101-120000"
    bak1.parent.mkdir()
    bak1.write_text("old content", encoding="utf-8")
    _make_old(bak1, days_old=30)

    bak2 = tmp_path / "output" / "foo" / "tools.py.bak-20250115-090000"
    bak2.parent.mkdir()
    bak2.write_text("old tools", encoding="utf-8")
    _make_old(bak2, days_old=30)

    summary = sweep_artifacts(tmp_path, older_than_days=7, dry_run=True)
    found_names = {p.name for p in summary["bak_files"]}
    assert "AGENT.md.bak-20250101-120000" in found_names
    assert "tools.py.bak-20250115-090000" in found_names
    assert summary["bytes"] > 0


def test_sweep_finds_builder_logs(tmp_path: Path):
    _seed_repo(tmp_path)
    log = tmp_path / "agent_builder" / "logs" / "builder-20250110-153000.log"
    log.write_text("log line\n", encoding="utf-8")
    _make_old(log, days_old=30)

    # A non-matching file should be ignored.
    other = tmp_path / "agent_builder" / "logs" / "not-a-builder-log.log"
    other.write_text("keep me", encoding="utf-8")
    _make_old(other, days_old=30)

    summary = sweep_artifacts(tmp_path, older_than_days=7, dry_run=True)
    assert len(summary["builder_logs"]) == 1
    assert summary["builder_logs"][0].name == "builder-20250110-153000.log"


def test_sweep_respects_older_than(tmp_path: Path):
    _seed_repo(tmp_path)
    recent = tmp_path / "agent_builder" / "x.bak-20260101-120000"
    recent.write_text("fresh", encoding="utf-8")
    _make_old(recent, days_old=2)  # younger than 7-day default

    old = tmp_path / "agent_builder" / "y.bak-20250101-120000"
    old.write_text("stale", encoding="utf-8")
    _make_old(old, days_old=30)

    summary = sweep_artifacts(tmp_path, older_than_days=7, dry_run=True)
    names = {p.name for p in summary["bak_files"]}
    assert "y.bak-20250101-120000" in names
    assert "x.bak-20260101-120000" not in names

    # Lower the cutoff to 1 day — now both qualify.
    summary2 = sweep_artifacts(tmp_path, older_than_days=1, dry_run=True)
    names2 = {p.name for p in summary2["bak_files"]}
    assert {"x.bak-20260101-120000", "y.bak-20250101-120000"}.issubset(names2)


def test_sweep_deletes_screenshots_directory_when_all_old(tmp_path: Path):
    _seed_repo(tmp_path)
    shots = tmp_path / "screenshots"
    shots.mkdir()
    f1 = shots / "one.png"
    f1.write_bytes(b"pixels")
    _make_old(f1, days_old=30)
    f2 = shots / "two.png"
    f2.write_bytes(b"more pixels")
    _make_old(f2, days_old=30)

    summary = sweep_artifacts(tmp_path, older_than_days=7, dry_run=False)
    assert summary["screenshots"] == shots
    assert not shots.exists()
    assert summary["bytes"] >= len(b"pixels") + len(b"more pixels")


def test_sweep_preserves_screenshots_when_some_are_recent(tmp_path: Path):
    _seed_repo(tmp_path)
    shots = tmp_path / "screenshots"
    shots.mkdir()
    old = shots / "old.png"
    old.write_bytes(b"stale")
    _make_old(old, days_old=30)
    fresh = shots / "fresh.png"
    fresh.write_bytes(b"new")
    # mtime is now → younger than 7 days

    summary = sweep_artifacts(tmp_path, older_than_days=7, dry_run=False)
    assert summary["screenshots"] is None
    assert shots.exists()
    assert fresh.exists()
    assert old.exists()  # we don't delete individual files inside screenshots/


def test_sweep_dry_run_does_not_delete(tmp_path: Path):
    _seed_repo(tmp_path)
    bak = tmp_path / "agent_builder" / "a.bak-20250101-120000"
    bak.write_text("old", encoding="utf-8")
    _make_old(bak, days_old=30)
    log = tmp_path / "agent_builder" / "logs" / "builder-20250101-120000.log"
    log.write_text("log", encoding="utf-8")
    _make_old(log, days_old=30)

    summary = sweep_artifacts(tmp_path, older_than_days=7, dry_run=True)
    assert len(summary["bak_files"]) == 1
    assert len(summary["builder_logs"]) == 1
    # Nothing was actually deleted
    assert bak.exists()
    assert log.exists()


def test_sweep_actually_deletes_when_not_dry_run(tmp_path: Path):
    _seed_repo(tmp_path)
    bak = tmp_path / "agent_builder" / "a.bak-20250101-120000"
    bak.write_text("old", encoding="utf-8")
    _make_old(bak, days_old=30)

    sweep_artifacts(tmp_path, older_than_days=7, dry_run=False)
    assert not bak.exists()
