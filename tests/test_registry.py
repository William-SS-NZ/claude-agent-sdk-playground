import pytest
import json
from pathlib import Path
from agent_builder.tools.registry import registry


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    path = tmp_path / "agents.json"
    path.write_text("[]", encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_add_agent(registry_path: Path):
    result = await registry({
        "action": "add",
        "agent_name": "test-agent",
        "description": "A test agent",
        "tools_list": ["greet", "farewell"],
    }, registry_file=str(registry_path))

    assert "is_error" not in result
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["name"] == "test-agent"
    assert data[0]["description"] == "A test agent"
    assert data[0]["tools"] == ["greet", "farewell"]
    assert "created" in data[0]
    assert data[0]["status"] == "active"


@pytest.mark.asyncio
async def test_list_agents(registry_path: Path):
    await registry({
        "action": "add",
        "agent_name": "agent-a",
        "description": "First",
        "tools_list": ["tool1"],
    }, registry_file=str(registry_path))
    await registry({
        "action": "add",
        "agent_name": "agent-b",
        "description": "Second",
        "tools_list": ["tool2"],
    }, registry_file=str(registry_path))

    result = await registry({"action": "list"}, registry_file=str(registry_path))
    text = result["content"][0]["text"]
    assert "agent-a" in text
    assert "agent-b" in text


@pytest.mark.asyncio
async def test_describe_agent(registry_path: Path):
    await registry({
        "action": "add",
        "agent_name": "my-agent",
        "description": "Does things",
        "tools_list": ["analyze"],
    }, registry_file=str(registry_path))

    result = await registry({
        "action": "describe",
        "agent_name": "my-agent",
    }, registry_file=str(registry_path))

    text = result["content"][0]["text"]
    assert "my-agent" in text
    assert "Does things" in text
    assert "analyze" in text


@pytest.mark.asyncio
async def test_describe_missing_agent(registry_path: Path):
    result = await registry({
        "action": "describe",
        "agent_name": "nonexistent",
    }, registry_file=str(registry_path))
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_list_empty_registry(registry_path: Path):
    result = await registry({"action": "list"}, registry_file=str(registry_path))
    text = result["content"][0]["text"]
    assert "No agents" in text


@pytest.mark.asyncio
async def test_add_dedupes_on_name(registry_path: Path):
    await registry({
        "action": "add", "agent_name": "dup", "description": "v1", "tools_list": ["a"],
    }, registry_file=str(registry_path))
    result = await registry({
        "action": "add", "agent_name": "dup", "description": "v2", "tools_list": ["a", "b"],
    }, registry_file=str(registry_path))
    assert "Updated" in result["content"][0]["text"]
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["description"] == "v2"
    assert data[0]["tools"] == ["a", "b"]


@pytest.mark.asyncio
async def test_remove_agent(registry_path: Path):
    await registry({
        "action": "add", "agent_name": "doomed", "description": "x", "tools_list": [],
    }, registry_file=str(registry_path))
    result = await registry({
        "action": "remove", "agent_name": "doomed",
    }, registry_file=str(registry_path))
    assert "is_error" not in result
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert data == []


@pytest.mark.asyncio
async def test_remove_missing_agent(registry_path: Path):
    result = await registry({
        "action": "remove", "agent_name": "nope",
    }, registry_file=str(registry_path))
    assert result.get("is_error") is True
