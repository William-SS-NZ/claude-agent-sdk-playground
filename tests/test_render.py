"""Tests for render_agent — rebuilds agent.py + AGENT.md from manifest."""

from pathlib import Path

import pytest

from agent_builder.render import _slug_to_module, render_agent
from agent_builder.manifest import Manifest, AttachedRecipe, save_manifest


@pytest.mark.asyncio
async def test_render_external_mcp_block_uses_json_encoding(tmp_path):
    """external_mcp_block entries must be JSON-encoded (double quotes) to match
    scaffold.py's external_mcps rendering. ``repr(dict)`` emits single-quoted
    Python literals which produces byte-diffs on otherwise-identical configs."""
    import json as _json
    agent_dir = await _scaffolded_agent(tmp_path)
    (agent_dir / "_recipes").mkdir(exist_ok=True)
    cfg = {"type": "stdio", "command": "echo", "args": ["x"]}
    (agent_dir / "_recipes" / "fake_mcp.mcp.json").write_text(
        _json.dumps(cfg), encoding="utf-8",
    )
    manifest = Manifest(
        agent_name="a",
        builder_version="0.9.0",
        recipes=[AttachedRecipe(
            name="fake-mcp", type="mcp", version="0.1.0",
            attached_at="2026-04-20",
        )],
    )
    save_manifest(agent_dir / ".recipe_manifest.json", manifest)

    render_agent(agent_dir)

    agent_py = (agent_dir / "agent.py").read_text()
    # JSON encoding: double-quoted keys + string values.
    assert '"fake_mcp": {"type": "stdio"' in agent_py
    # Must not use Python repr which emits single quotes.
    assert "'type': 'stdio'" not in agent_py


def test_slug_to_module_handles_digit_leading():
    """Slug regex allows ``^[a-z0-9]...`` but Python module names may not
    start with a digit — ensure the helper prepends ``_`` so the emitted
    ``from _recipes.<mod> import ...`` line stays importable."""
    assert _slug_to_module("telegram-poll") == "telegram_poll"
    assert _slug_to_module("3rd-party-tool") == "_3rd_party_tool"
    assert _slug_to_module("9") == "_9"
    assert _slug_to_module("abc-123") == "abc_123"


async def _scaffolded_agent(tmp_path: Path) -> Path:
    """Helper: produce a just-scaffolded agent dir with minimal file surface."""
    from agent_builder.tools.scaffold import scaffold_agent
    out = tmp_path / "output"
    out.mkdir()
    await scaffold_agent({"agent_name": "a", "description": "x"}, output_base=str(out))
    return out / "a"


def _scaffolded_agent_sync(tmp_path: Path) -> Path:
    """Sync variant for non-async tests."""
    from agent_builder.tools.scaffold import scaffold_agent
    import asyncio
    out = tmp_path / "output"
    out.mkdir()
    asyncio.run(scaffold_agent({"agent_name": "a", "description": "x"}, output_base=str(out)))
    return out / "a"


@pytest.mark.asyncio
async def test_render_with_empty_manifest_produces_valid_agent_py(tmp_path):
    agent_dir = await _scaffolded_agent(tmp_path)
    manifest = Manifest(agent_name="a", builder_version="0.9.0")
    save_manifest(agent_dir / ".recipe_manifest.json", manifest)

    render_agent(agent_dir)

    agent_py = (agent_dir / "agent.py").read_text()
    assert "RECIPE_PINS = {}" in agent_py
    assert '"agent_tools": tools_server' in agent_py
    # No recipe imports block
    assert "# --- recipe servers ---" in agent_py  # banner still present, empty body below
    # Placeholders fully substituted
    assert "{{" not in agent_py


@pytest.mark.asyncio
async def test_render_with_tool_recipe_emits_import_and_server_entry(tmp_path):
    agent_dir = await _scaffolded_agent(tmp_path)
    (agent_dir / "_recipes").mkdir()
    (agent_dir / "_recipes" / "telegram_poll.py").write_text(
        'from claude_agent_sdk import create_sdk_mcp_server\n'
        'tools_server = create_sdk_mcp_server(name="telegram_poll", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    manifest = Manifest(
        agent_name="a",
        builder_version="0.9.0",
        recipes=[AttachedRecipe(
            name="telegram-poll", type="tool", version="0.1.0", attached_at="2026-04-20",
        )],
    )
    save_manifest(agent_dir / ".recipe_manifest.json", manifest)

    render_agent(agent_dir)

    agent_py = (agent_dir / "agent.py").read_text()
    assert "from _recipes.telegram_poll import tools_server as telegram_poll_server" in agent_py
    assert '"telegram_poll": telegram_poll_server' in agent_py
    assert '"telegram-poll": "0.1.0"' in agent_py  # in RECIPE_PINS


@pytest.mark.asyncio
async def test_render_fills_poll_source_from_manifest(tmp_path):
    """Poll-mode agent rendered with manifest.poll_source = "telegram-poll"
    emits the correct import and expression in place of the stub."""
    from agent_builder.tools.scaffold import scaffold_agent
    out = tmp_path / "output"
    out.mkdir()
    await scaffold_agent(
        {"agent_name": "pa", "description": "x", "mode": "poll"},
        output_base=str(out),
    )
    agent_dir = out / "pa"

    # Fake _recipes/telegram_poll.py — render doesn't need the full recipe to test rendering.
    (agent_dir / "_recipes").mkdir(exist_ok=True)
    (agent_dir / "_recipes" / "telegram_poll.py").write_text(
        'from claude_agent_sdk import create_sdk_mcp_server\n'
        'async def telegram_poll_source():\n'
        '    if False: yield None\n'
        'tools_server = create_sdk_mcp_server(name="telegram_poll", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )

    manifest = Manifest(
        agent_name="pa",
        builder_version="0.9.0",
        recipes=[AttachedRecipe(
            name="telegram-poll", type="tool", version="0.1.0", attached_at="2026-04-20",
        )],
        poll_source="telegram-poll",
    )
    save_manifest(agent_dir / ".recipe_manifest.json", manifest)

    render_agent(agent_dir)

    agent_py = (agent_dir / "agent.py").read_text(encoding="utf-8")
    assert "from _recipes.telegram_poll import telegram_poll_source" in agent_py
    assert "telegram_poll_source()" in agent_py
    # Stub expression gone from assignment line.
    assign_line = next(l for l in agent_py.splitlines() if l.lstrip().startswith("poll_source ="))
    assert "_stub_poll_source" not in assign_line


@pytest.mark.asyncio
async def test_render_poll_source_default_stub_when_unset(tmp_path):
    """When manifest.poll_source is empty, render emits the stub call."""
    from agent_builder.tools.scaffold import scaffold_agent
    out = tmp_path / "output"
    out.mkdir()
    await scaffold_agent(
        {"agent_name": "pb", "description": "x", "mode": "poll"},
        output_base=str(out),
    )
    agent_dir = out / "pb"

    manifest = Manifest(agent_name="pb", builder_version="0.9.0")
    save_manifest(agent_dir / ".recipe_manifest.json", manifest)

    render_agent(agent_dir)

    agent_py = (agent_dir / "agent.py").read_text(encoding="utf-8")
    assert "_stub_poll_source()" in agent_py


def test_render_preserves_user_additions_slot(tmp_path):
    agent_dir = _scaffolded_agent_sync(tmp_path)
    manifest = Manifest(agent_name="a", builder_version="0.9.0")
    save_manifest(agent_dir / ".recipe_manifest.json", manifest)
    # Seed AGENT.md with user content in the slot
    (agent_dir / "AGENT.md").write_text(
        "# Agent\n\n"
        "## Purpose\nRendered.\n\n"
        "<!-- SLOT: builder_agent_additions -->\n"
        "<!-- /SLOT: builder_agent_additions -->\n\n"
        "<!-- SLOT: user_additions -->\n"
        "Hand-written note that must survive.\n"
        "<!-- /SLOT: user_additions -->\n",
        encoding="utf-8",
    )

    render_agent(agent_dir)

    content = (agent_dir / "AGENT.md").read_text()
    assert "Hand-written note that must survive." in content
