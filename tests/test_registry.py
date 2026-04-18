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


@pytest.mark.asyncio
async def test_add_persists_sdk_config_fields(registry_path: Path):
    await registry({
        "action": "add",
        "agent_name": "configured",
        "description": "has sdk config",
        "tools_list": ["Read"],
        "max_turns": 42,
        "max_budget_usd": 2.50,
        "permission_mode": "bypassPermissions",
    }, registry_file=str(registry_path))

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert data[0]["max_turns"] == 42
    assert data[0]["max_budget_usd"] == 2.50
    assert data[0]["permission_mode"] == "bypassPermissions"


@pytest.mark.asyncio
async def test_add_sets_updated_at_equal_to_created_on_fresh_entry(registry_path: Path):
    await registry({
        "action": "add", "agent_name": "fresh", "description": "x", "tools_list": [],
    }, registry_file=str(registry_path))

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert data[0]["created"] == data[0]["updated_at"]


@pytest.mark.asyncio
async def test_add_preserves_created_but_refreshes_updated_at(registry_path: Path):
    # Seed an entry with a stale created date.
    registry_path.write_text(json.dumps([{
        "name": "aged",
        "description": "old",
        "tools": [],
        "created": "2020-01-01",
        "updated_at": "2020-01-01",
        "path": "output/aged/",
        "status": "active",
    }]), encoding="utf-8")

    await registry({
        "action": "add", "agent_name": "aged", "description": "new", "tools_list": ["x"],
    }, registry_file=str(registry_path))

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert data[0]["created"] == "2020-01-01"  # unchanged
    assert data[0]["updated_at"] != "2020-01-01"  # refreshed


@pytest.mark.asyncio
async def test_describe_includes_sdk_config_fields(registry_path: Path):
    await registry({
        "action": "add",
        "agent_name": "shown",
        "description": "d",
        "tools_list": ["Read"],
        "max_turns": 17,
        "max_budget_usd": 0.75,
        "permission_mode": "acceptEdits",
    }, registry_file=str(registry_path))

    result = await registry({
        "action": "describe", "agent_name": "shown",
    }, registry_file=str(registry_path))

    text = result["content"][0]["text"]
    assert "max_turns" in text
    assert "17" in text
    assert "max_budget_usd" in text
    assert "0.75" in text
    assert "permission_mode" in text
    assert "acceptEdits" in text
    assert "updated_at" in text


@pytest.mark.asyncio
async def test_old_shape_entry_still_loads(registry_path: Path):
    # Write a registry entry written by a pre-updated_at version.
    registry_path.write_text(json.dumps([{
        "name": "legacy",
        "description": "old shape",
        "tools": ["a"],
        "created": "2024-06-01",
        "path": "output/legacy/",
        "status": "active",
    }]), encoding="utf-8")

    list_result = await registry({"action": "list"}, registry_file=str(registry_path))
    assert "legacy" in list_result["content"][0]["text"]

    describe_result = await registry({
        "action": "describe", "agent_name": "legacy",
    }, registry_file=str(registry_path))
    assert "is_error" not in describe_result
    text = describe_result["content"][0]["text"]
    assert "legacy" in text
    # updated_at falls back to created when missing
    assert "2024-06-01" in text


@pytest.mark.asyncio
async def test_add_update_preserves_sdk_config_when_not_resupplied(registry_path: Path):
    await registry({
        "action": "add",
        "agent_name": "sticky",
        "description": "v1",
        "tools_list": ["a"],
        "max_turns": 99,
        "permission_mode": "plan",
    }, registry_file=str(registry_path))

    # Second call without the SDK-config fields should keep them intact.
    await registry({
        "action": "add",
        "agent_name": "sticky",
        "description": "v2",
        "tools_list": ["a", "b"],
    }, registry_file=str(registry_path))

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert data[0]["description"] == "v2"
    assert data[0]["max_turns"] == 99
    assert data[0]["permission_mode"] == "plan"
