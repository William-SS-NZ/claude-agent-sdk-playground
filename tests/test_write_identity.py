import pytest
from pathlib import Path
from agent_builder.tools.write_identity import write_identity


@pytest.mark.asyncio
async def test_writes_all_identity_files(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    result = await write_identity({
        "agent_name": "test-agent",
        "agent_md": "# Agent\nYou review code.",
        "soul_md": "# Soul\nBe thorough.",
        "memory_md": "# Memory\nNo context yet.",
        "user_md": None,
    }, output_base=str(tmp_path))

    assert (agent_dir / "AGENT.md").read_text(encoding="utf-8") == "# Agent\nYou review code."
    assert (agent_dir / "SOUL.md").read_text(encoding="utf-8") == "# Soul\nBe thorough."
    assert (agent_dir / "MEMORY.md").read_text(encoding="utf-8") == "# Memory\nNo context yet."
    assert not (agent_dir / "USER.md").exists()
    assert "is_error" not in result


@pytest.mark.asyncio
async def test_writes_user_md_when_provided(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    await write_identity({
        "agent_name": "test-agent",
        "agent_md": "# Agent",
        "soul_md": "# Soul",
        "memory_md": "# Memory",
        "user_md": "# User\nName: William",
    }, output_base=str(tmp_path))

    assert (agent_dir / "USER.md").read_text(encoding="utf-8") == "# User\nName: William"


@pytest.mark.asyncio
async def test_reports_char_count(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    result = await write_identity({
        "agent_name": "test-agent",
        "agent_md": "A" * 100,
        "soul_md": "B" * 200,
        "memory_md": "C" * 50,
        "user_md": None,
    }, output_base=str(tmp_path))

    text = result["content"][0]["text"]
    assert "350" in text


def test_mcp_schema_exposes_user_md():
    """Regression: schema used to omit user_md, making the USER.md code path
    unreachable via the SDK even though the function accepted it."""
    from agent_builder.tools.write_identity import write_identity_tool

    # MCP tool wrapper may store schema under different attr names depending
    # on SDK version; dig for any dict-shaped property list.
    attrs_to_try = ("_schema", "schema", "input_schema", "inputSchema", "__claude_tool_schema__")
    schema = None
    for name in attrs_to_try:
        val = getattr(write_identity_tool, name, None)
        if isinstance(val, dict):
            schema = val
            break
    if schema is None:
        # Fall back to scanning the whole object's __dict__ for any dict that
        # looks like a schema (has a 'properties' or is a flat kwargs dict).
        for v in vars(write_identity_tool).values():
            if isinstance(v, dict) and ("user_md" in v or "properties" in v):
                schema = v
                break
    assert schema is not None, "could not locate schema on write_identity_tool"

    # Flattened {agent_name: str, ...} form OR JSON-schema {properties: {...}} form.
    if "properties" in schema:
        assert "user_md" in schema["properties"], f"user_md missing from schema: {schema}"
    else:
        assert "user_md" in schema, f"user_md missing from schema: {schema}"


@pytest.mark.asyncio
async def test_errors_on_missing_directory(tmp_path: Path):
    result = await write_identity({
        "agent_name": "nonexistent",
        "agent_md": "# Agent",
        "soul_md": "# Soul",
        "memory_md": "# Memory",
        "user_md": None,
    }, output_base=str(tmp_path))

    assert result.get("is_error") is True
