import pytest
from pathlib import Path
from agent_builder.tools.scaffold import scaffold_agent


@pytest.mark.asyncio
async def test_scaffold_creates_directory_and_files(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "test-agent", "description": "A test agent"},
        output_base=str(tmp_path),
    )
    content = result["content"][0]["text"]
    agent_dir = tmp_path / "test-agent"

    assert agent_dir.exists()
    assert (agent_dir / "agent.py").exists()
    assert (agent_dir / ".env.example").exists()
    assert (agent_dir / ".gitignore").exists()
    assert "test-agent" in (agent_dir / "agent.py").read_text(encoding="utf-8")
    assert "Created" in content


@pytest.mark.asyncio
async def test_scaffold_rejects_invalid_name(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "../escape", "description": "bad"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True
    assert "Invalid" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_scaffold_rejects_dotdot_in_name(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "foo..bar", "description": "bad"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_scaffold_rejects_uppercase(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "MyAgent", "description": "bad"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_scaffold_rejects_existing_directory(tmp_path: Path):
    (tmp_path / "existing-agent").mkdir()
    result = await scaffold_agent(
        {"agent_name": "existing-agent", "description": "dup"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True
    assert "exists" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_scaffold_gitignore_contents(tmp_path: Path):
    await scaffold_agent(
        {"agent_name": "test-agent", "description": "test"},
        output_base=str(tmp_path),
    )
    gitignore = (tmp_path / "test-agent" / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "__pycache__" in gitignore
    assert "CLAUDE.md" in gitignore
