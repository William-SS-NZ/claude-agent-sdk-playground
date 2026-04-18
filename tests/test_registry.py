import pytest
import json
from pathlib import Path
from agent_builder.tools import registry as registry_mod
from agent_builder.tools.registry import registry, REQUIRED_AGENT_FILES


@pytest.fixture(autouse=True)
def _disable_registry_validation(monkeypatch):
    """The existing tests in this file exercise registry's bookkeeping in
    isolation; they don't seed an output/<name>/ dir for every agent. The
    new `add`-time completeness check is exercised separately in
    test_registry_validation_*; here we no-op it so legacy tests stay
    focused on the registry semantics they were written for."""
    monkeypatch.setattr(registry_mod, "_verify_agent_complete", lambda *_a, **_kw: [])


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    path = tmp_path / "agents.json"
    path.write_text("[]", encoding="utf-8")
    return path


@pytest.fixture
def output_base(tmp_path: Path) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    return base


def _seed_complete_agent(output_base: Path, name: str) -> Path:
    """Create the minimum file set registry.add validates against."""
    agent_dir = output_base / name
    agent_dir.mkdir()
    for f in REQUIRED_AGENT_FILES:
        (agent_dir / f).write_text("# stub", encoding="utf-8")
    return agent_dir


async def _add_complete(registry_path: Path, output_base: Path, **kwargs):
    """Helper for tests that don't care about validation — seeds files first."""
    name = kwargs["agent_name"]
    if not (output_base / name).exists():
        _seed_complete_agent(output_base, name)
    return await registry(
        {"action": "add", **kwargs},
        registry_file=str(registry_path),
        output_base=str(output_base),
    )


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


# --- Build-completeness validation tests ---
# These use the un-monkeypatched validator on purpose, so they bypass the
# autouse fixture by running validation directly + by passing real dirs.

def test_verify_agent_complete_lists_missing_files(tmp_path: Path, monkeypatch):
    monkeypatch.undo()  # bypass the module-wide validation no-op
    base = tmp_path / "output"
    base.mkdir()
    (base / "incomplete").mkdir()
    (base / "incomplete" / "agent.py").write_text("# stub", encoding="utf-8")
    (base / "incomplete" / "AGENT.md").write_text("# stub", encoding="utf-8")

    missing = registry_mod._verify_agent_complete("incomplete", str(base))
    assert "tools.py" in missing
    assert "SOUL.md" in missing
    assert "MEMORY.md" in missing
    assert "agent.py" not in missing


def test_verify_agent_complete_returns_empty_when_dir_missing_entirely(tmp_path: Path, monkeypatch):
    monkeypatch.undo()
    base = tmp_path / "output"
    base.mkdir()
    missing = registry_mod._verify_agent_complete("ghost", str(base))
    # Whole dir missing = every required file is missing
    assert set(missing) == set(REQUIRED_AGENT_FILES)


@pytest.mark.asyncio
async def test_add_refuses_incomplete_build(tmp_path: Path, monkeypatch):
    # Disable the autouse no-op so real validation runs for this test.
    monkeypatch.undo()
    base = tmp_path / "output"
    base.mkdir()
    (base / "halfbuilt").mkdir()
    (base / "halfbuilt" / "agent.py").write_text("# stub", encoding="utf-8")
    (base / "halfbuilt" / "AGENT.md").write_text("# stub", encoding="utf-8")
    # Missing tools.py, SOUL.md, MEMORY.md

    reg_path = tmp_path / "agents.json"
    reg_path.write_text("[]", encoding="utf-8")

    result = await registry(
        {"action": "add", "agent_name": "halfbuilt", "description": "x"},
        registry_file=str(reg_path),
        output_base=str(base),
    )

    assert result.get("is_error") is True
    text = result["content"][0]["text"]
    assert "tools.py" in text
    assert "SOUL.md" in text
    # Registry not modified
    assert json.loads(reg_path.read_text(encoding="utf-8")) == []


@pytest.mark.asyncio
async def test_add_accepts_complete_build(tmp_path: Path, monkeypatch):
    monkeypatch.undo()
    base = tmp_path / "output"
    base.mkdir()
    agent_dir = base / "complete"
    agent_dir.mkdir()
    for f in REQUIRED_AGENT_FILES:
        (agent_dir / f).write_text("# stub", encoding="utf-8")

    reg_path = tmp_path / "agents.json"
    reg_path.write_text("[]", encoding="utf-8")

    result = await registry(
        {"action": "add", "agent_name": "complete", "description": "y", "tools_list": ["x"]},
        registry_file=str(reg_path),
        output_base=str(base),
    )

    assert "is_error" not in result
    data = json.loads(reg_path.read_text(encoding="utf-8"))
    assert len(data) == 1 and data[0]["name"] == "complete"
