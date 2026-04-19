"""Tests for the attach_recipe builder tool (composition model)."""

import json
import time
from pathlib import Path

import pytest

from agent_builder.tools.attach_recipe import attach_recipe
from agent_builder.manifest import MANIFEST_FILENAME

FIXTURES = Path(__file__).parent / "fixtures" / "recipes_valid"


@pytest.fixture
def agent_dir(tmp_path):
    """Simulate a just-scaffolded agent dir with manifest + render-ready agent.py."""
    from agent_builder.tools.scaffold import scaffold_agent
    import asyncio
    out = tmp_path / "output"
    out.mkdir()
    asyncio.run(scaffold_agent(
        {"agent_name": "test-agent", "description": "test"},
        output_base=str(out),
    ))
    return out / "test-agent"


@pytest.mark.asyncio
async def test_attach_tool_recipe_copies_code(agent_dir):
    result = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "hello-world"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert result.get("is_error") is not True, result["content"][0]["text"]

    # Composition: recipe source is copied into _recipes/<slug>.py
    recipe_file = agent_dir / "_recipes" / "hello_world.py"
    assert recipe_file.exists()
    assert "async def hello" in recipe_file.read_text(encoding="utf-8")

    # render_agent rewrites agent.py — the import + server entry appear.
    agent_py = (agent_dir / "agent.py").read_text(encoding="utf-8")
    assert "from _recipes.hello_world import tools_server as hello_world_server" in agent_py

    # Manifest is updated.
    manifest = json.loads((agent_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    recipe_names = [r["name"] for r in manifest["recipes"]]
    assert "hello-world" in recipe_names
    hello_entry = next(r for r in manifest["recipes"] if r["name"] == "hello-world")
    assert hello_entry["version"] == "0.1.0"
    assert hello_entry["type"] == "tool"


@pytest.mark.asyncio
async def test_attach_tool_recipe_idempotent(agent_dir):
    first = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "hello-world"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert first.get("is_error") is not True

    manifest_before = (agent_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    recipe_mtime_before = (agent_dir / "_recipes" / "hello_world.py").stat().st_mtime

    # Tiny sleep so a non-idempotent implementation would produce a different mtime.
    time.sleep(0.05)

    second = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "hello-world"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert second.get("is_error") is not True

    manifest_after = (agent_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    recipe_mtime_after = (agent_dir / "_recipes" / "hello_world.py").stat().st_mtime

    assert manifest_before == manifest_after
    # Early-return on same version means we do not rewrite the recipe file.
    assert recipe_mtime_before == recipe_mtime_after


@pytest.mark.asyncio
async def test_attach_unknown_recipe_errors(agent_dir):
    result = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "does-not-exist"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert result["is_error"] is True
    assert "does-not-exist" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_attach_rejects_path_traversal(agent_dir):
    result = await attach_recipe(
        {"agent_name": "../escape", "recipe_name": "hello-world"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert result["is_error"] is True
