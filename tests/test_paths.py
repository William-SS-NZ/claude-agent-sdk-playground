"""Tests for the shared path validator in agent_builder/paths.py.

Four separate tools (scaffold, remove_agent, rollback, self_heal) each had
their own near-identical path-containment logic. This module consolidates
them. These tests pin down the semantic contract so the per-tool migrations
stay behaviour-preserving.
"""

from pathlib import Path

import pytest

from agent_builder.paths import validate_relative_to_base


def test_relative_inside_base_ok(tmp_path: Path) -> None:
    base = tmp_path
    (base / "sub").mkdir()
    resolved, err = validate_relative_to_base(str(base / "sub"), [base])
    assert err is None
    assert resolved == (base / "sub").resolve()


def test_parent_escape_rejected(tmp_path: Path) -> None:
    base = tmp_path / "inner"
    base.mkdir()
    # ../sibling escapes `inner`.
    _, err = validate_relative_to_base(str(base / ".." / "sibling"), [base])
    assert err is not None
    lower = err.lower()
    assert "outside" in lower or "traversal" in lower or "escape" in lower


def test_absolute_path_outside_rejected(tmp_path: Path) -> None:
    base = tmp_path
    # Anywhere that's clearly not under tmp_path.
    other = Path(__file__).resolve().parent
    # Make sure it's not coincidentally inside base (tmp_path is in a
    # different directory tree anyway).
    assert base.resolve() not in other.parents and other != base.resolve()
    _, err = validate_relative_to_base(str(other), [base])
    assert err is not None


def test_multiple_allowed_bases(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    resolved, err = validate_relative_to_base(str(b / "inside"), [a, b])
    assert err is None
    assert resolved == (b / "inside").resolve()


def test_null_bytes_rejected(tmp_path: Path) -> None:
    _, err = validate_relative_to_base("foo\x00bar", [tmp_path])
    assert err is not None


def test_inside_returns_resolved_path(tmp_path: Path) -> None:
    """Sanity check: resolution is returned even when the target doesn't exist."""
    base = tmp_path
    resolved, err = validate_relative_to_base(str(base / "nonexistent"), [base])
    assert err is None
    assert resolved == (base / "nonexistent").resolve()


def test_first_matching_base_wins(tmp_path: Path) -> None:
    """When multiple bases overlap, the first match short-circuits."""
    outer = tmp_path
    inner = tmp_path / "nested"
    inner.mkdir()
    # `inner/foo` is under both outer and inner.
    resolved, err = validate_relative_to_base(str(inner / "foo"), [outer, inner])
    assert err is None
    assert resolved == (inner / "foo").resolve()
