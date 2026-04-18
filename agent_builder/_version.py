"""Single source of truth for the Agent Builder version.

Reads the installed package metadata via importlib.metadata so we stay in lockstep
with pyproject.toml. Falls back to "unknown" when the package hasn't been
installed (e.g. running from a fresh source checkout with no `pip install -e .`),
so imports never fail at module load time.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("claude-agent-sdk-playground")
except PackageNotFoundError:  # pragma: no cover - exercised in tests via monkeypatch
    __version__ = "unknown"
