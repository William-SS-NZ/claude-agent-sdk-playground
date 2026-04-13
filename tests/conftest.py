import pytest
from pathlib import Path


@pytest.fixture
def tmp_agent_dir(tmp_path: Path) -> Path:
    """Create a temporary agent directory with sample identity files."""
    identity_dir = tmp_path / "identity"
    identity_dir.mkdir()

    (identity_dir / "AGENT.md").write_text("# Agent\nYou are a test agent.", encoding="utf-8")
    (identity_dir / "SOUL.md").write_text("# Soul\nBe helpful and concise.", encoding="utf-8")
    (identity_dir / "MEMORY.md").write_text("# Memory\nNo prior context.", encoding="utf-8")

    return tmp_path


@pytest.fixture
def tmp_agent_dir_with_user(tmp_agent_dir: Path) -> Path:
    """Same as tmp_agent_dir but includes USER.md."""
    identity_dir = tmp_agent_dir / "identity"
    (identity_dir / "USER.md").write_text("# User\nName: William", encoding="utf-8")
    return tmp_agent_dir
