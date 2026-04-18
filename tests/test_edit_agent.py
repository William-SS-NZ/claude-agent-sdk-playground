from pathlib import Path

import pytest

from agent_builder.tools.edit_agent import edit_agent


def _seed_agent(output_base: Path, name: str) -> Path:
    agent_dir = output_base / name
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text("# Agent v1", encoding="utf-8")
    (agent_dir / "SOUL.md").write_text("# Soul v1", encoding="utf-8")
    (agent_dir / "MEMORY.md").write_text("# Memory v1", encoding="utf-8")
    (agent_dir / "tools.py").write_text("# original tools", encoding="utf-8")
    return agent_dir


@pytest.fixture
def output_base(tmp_path: Path) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    return base


@pytest.mark.asyncio
async def test_edit_agent_updates_only_supplied_identity_fields(output_base: Path):
    agent_dir = _seed_agent(output_base, "target")

    result = await edit_agent(
        {"agent_name": "target", "agent_md": "# Agent v2"},
        output_base=str(output_base),
    )

    assert "is_error" not in result
    assert (agent_dir / "AGENT.md").read_text(encoding="utf-8") == "# Agent v2"
    assert (agent_dir / "SOUL.md").read_text(encoding="utf-8") == "# Soul v1"
    assert (agent_dir / "MEMORY.md").read_text(encoding="utf-8") == "# Memory v1"


@pytest.mark.asyncio
async def test_edit_agent_writes_backup(output_base: Path):
    agent_dir = _seed_agent(output_base, "target")

    await edit_agent(
        {"agent_name": "target", "agent_md": "# Agent v2"},
        output_base=str(output_base),
    )

    backups = list(agent_dir.glob("AGENT.md.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "# Agent v1"


@pytest.mark.asyncio
async def test_edit_agent_replaces_tools_with_header(output_base: Path):
    agent_dir = _seed_agent(output_base, "target")

    result = await edit_agent(
        {"agent_name": "target", "tools_code": "# brand new tools"},
        output_base=str(output_base),
    )

    assert "is_error" not in result
    new = (agent_dir / "tools.py").read_text(encoding="utf-8")
    assert "# brand new tools" in new
    assert "TEST_MODE = False" in new  # header prepended
    assert "from claude_agent_sdk" in new


@pytest.mark.asyncio
async def test_edit_agent_rejects_nonexistent_agent(output_base: Path):
    result = await edit_agent(
        {"agent_name": "ghost", "agent_md": "# x"},
        output_base=str(output_base),
    )
    assert result.get("is_error") is True
    assert "not found" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_edit_agent_rejects_invalid_name(output_base: Path):
    result = await edit_agent(
        {"agent_name": "../escape", "agent_md": "# x"},
        output_base=str(output_base),
    )
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_edit_agent_empty_update_errors(output_base: Path):
    _seed_agent(output_base, "target")
    result = await edit_agent(
        {"agent_name": "target"},
        output_base=str(output_base),
    )
    assert result.get("is_error") is True
    assert "nothing" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_edit_agent_creates_user_md_when_first_supplied(output_base: Path):
    agent_dir = _seed_agent(output_base, "target")
    assert not (agent_dir / "USER.md").exists()

    result = await edit_agent(
        {"agent_name": "target", "user_md": "# User\nName: W"},
        output_base=str(output_base),
    )

    assert "is_error" not in result
    assert (agent_dir / "USER.md").read_text(encoding="utf-8") == "# User\nName: W"
    # No backup because USER.md didn't exist before
    assert not list(agent_dir.glob("USER.md.bak-*"))
