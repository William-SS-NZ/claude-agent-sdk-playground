import json
from pathlib import Path

import pytest

from agent_builder.tools.remove_agent import remove_agent


@pytest.fixture
def output_base(tmp_path: Path) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    return base


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    path = tmp_path / "agents.json"
    path.write_text("[]", encoding="utf-8")
    return path


def _seed_agent(output_base: Path, name: str) -> Path:
    agent_dir = output_base / name
    agent_dir.mkdir()
    (agent_dir / "agent.py").write_text("# stub", encoding="utf-8")
    (agent_dir / "AGENT.md").write_text("# stub", encoding="utf-8")
    return agent_dir


def _seed_registry(registry_path: Path, names: list[str]) -> None:
    entries = [{"name": n, "description": "", "tools": [], "created": "2026-04-18", "path": f"output/{n}/", "status": "active"} for n in names]
    registry_path.write_text(json.dumps(entries), encoding="utf-8")


@pytest.mark.asyncio
async def test_remove_deletes_directory_and_registry_entry(output_base: Path, registry_path: Path):
    agent_dir = _seed_agent(output_base, "doomed")
    _seed_registry(registry_path, ["doomed", "other"])

    result = await remove_agent(
        {"agent_name": "doomed"},
        output_base=str(output_base),
        registry_file=str(registry_path),
    )

    assert "is_error" not in result
    assert not agent_dir.exists()
    remaining = json.loads(registry_path.read_text(encoding="utf-8"))
    assert [a["name"] for a in remaining] == ["other"]


@pytest.mark.asyncio
async def test_remove_rejects_path_traversal(output_base: Path, registry_path: Path, tmp_path: Path):
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (sibling / "sentinel.txt").write_text("keep me", encoding="utf-8")

    result = await remove_agent(
        {"agent_name": "../sibling"},
        output_base=str(output_base),
        registry_file=str(registry_path),
    )

    assert result.get("is_error") is True
    assert sibling.exists()
    assert (sibling / "sentinel.txt").exists()


@pytest.mark.asyncio
async def test_remove_rejects_invalid_name(output_base: Path, registry_path: Path):
    result = await remove_agent(
        {"agent_name": "Bad Name"},
        output_base=str(output_base),
        registry_file=str(registry_path),
    )
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_remove_missing_agent(output_base: Path, registry_path: Path):
    result = await remove_agent(
        {"agent_name": "nonexistent"},
        output_base=str(output_base),
        registry_file=str(registry_path),
    )
    assert result.get("is_error") is True
    assert "nothing to remove" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_remove_directory_only(output_base: Path, registry_path: Path):
    agent_dir = _seed_agent(output_base, "orphan")

    result = await remove_agent(
        {"agent_name": "orphan"},
        output_base=str(output_base),
        registry_file=str(registry_path),
    )

    assert "is_error" not in result
    assert not agent_dir.exists()


@pytest.mark.asyncio
async def test_remove_registry_entry_only(output_base: Path, registry_path: Path):
    _seed_registry(registry_path, ["ghost"])

    result = await remove_agent(
        {"agent_name": "ghost"},
        output_base=str(output_base),
        registry_file=str(registry_path),
    )

    assert "is_error" not in result
    remaining = json.loads(registry_path.read_text(encoding="utf-8"))
    assert remaining == []
