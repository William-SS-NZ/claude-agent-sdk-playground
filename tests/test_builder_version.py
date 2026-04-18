"""Tests for agent_builder._version — the single source of truth for the
builder's version string, used both to stamp generated agents and to version
the builder's own MCP server."""

import importlib

import pytest


def test_version_is_non_empty_string():
    """When the package is installed (as it is in CI / dev), __version__ must
    surface as a non-empty string pulled from pyproject metadata."""
    from agent_builder._version import __version__

    assert isinstance(__version__, str)
    assert __version__ != ""


def test_version_matches_pyproject_when_installed():
    """If the package metadata is available, __version__ must equal it
    (not some hardcoded drift)."""
    from importlib.metadata import PackageNotFoundError, version as pkg_version

    try:
        expected = pkg_version("claude-agent-sdk-playground")
    except PackageNotFoundError:
        pytest.skip("package not installed — fallback path covered elsewhere")

    from agent_builder._version import __version__
    assert __version__ == expected


def test_version_falls_back_to_unknown_when_metadata_missing(monkeypatch: pytest.MonkeyPatch):
    """Running from a source checkout that was never pip-installed must not
    crash on import — _version falls back to the sentinel 'unknown'."""
    import importlib.metadata as _md

    def _raise(_name):
        raise _md.PackageNotFoundError("claude-agent-sdk-playground")

    monkeypatch.setattr(_md, "version", _raise)

    # Force a fresh import so the try/except executes against the patched metadata.
    import agent_builder._version as version_mod
    reloaded = importlib.reload(version_mod)

    try:
        assert reloaded.__version__ == "unknown"
    finally:
        # Undo the monkeypatch *before* reloading, otherwise the reload keeps
        # seeing the raising stub and the "fallback" value sticks around for
        # every subsequent test.
        monkeypatch.undo()
        importlib.reload(version_mod)
