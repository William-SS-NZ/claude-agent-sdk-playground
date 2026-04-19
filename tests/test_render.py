"""Tests for render_agent — rebuilds agent.py + AGENT.md from manifest."""

from pathlib import Path

import pytest

from agent_builder.render import render_agent
from agent_builder.manifest import Manifest, AttachedRecipe, save_manifest


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
