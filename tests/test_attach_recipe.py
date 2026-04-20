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


@pytest.fixture
def poll_agent_dir(tmp_path):
    """Scaffold a poll-mode agent so we can attach poll-capable recipes."""
    from agent_builder.tools.scaffold import scaffold_agent
    import asyncio
    out = tmp_path / "output"
    out.mkdir()
    asyncio.run(scaffold_agent(
        {"agent_name": "poll-agent", "description": "poll", "mode": "poll"},
        output_base=str(out),
    ))
    return out / "poll-agent"


@pytest.mark.asyncio
async def test_attach_telegram_poll_sets_manifest_poll_source(poll_agent_dir):
    """Attaching a poll_source recipe records it in manifest.poll_source and
    rewrites agent.py to import telegram_poll_source from the _recipes module."""
    from agent_builder.recipes.loader import default_recipes_root

    result = await attach_recipe(
        {"agent_name": "poll-agent", "recipe_name": "telegram-poll"},
        output_base=str(poll_agent_dir.parent),
        recipes_root=default_recipes_root(),
    )
    assert result.get("is_error") is not True, result["content"][0]["text"]

    manifest = json.loads((poll_agent_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["poll_source"] == "telegram-poll"

    agent_py = (poll_agent_dir / "agent.py").read_text(encoding="utf-8")
    assert "from _recipes.telegram_poll import telegram_poll_source" in agent_py
    # The stub expression should be gone — actual poll source takes its place.
    assert "_stub_poll_source()" not in agent_py.split("poll_source =", 1)[-1].splitlines()[0]
    # The actual poll-source call line appears.
    assert "telegram_poll_source()" in agent_py


@pytest.mark.asyncio
async def test_attach_mcp_recipe_inlines_into_agent_py(agent_dir):
    result = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "fake-mcp"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert result.get("is_error") is not True, result
    agent_py = (agent_dir / "agent.py").read_text()
    assert '"fake-mcp"' in agent_py or '"fake_mcp"' in agent_py
    env_ex = (agent_dir / ".env.example").read_text()
    assert "FAKE_TOKEN" in env_ex
    assert "# --- from recipe: fake-mcp @ 0.1.0 ---" in env_ex


@pytest.mark.asyncio
async def test_attach_mcp_recipe_idempotent(agent_dir):
    await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "fake-mcp"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    env_ex_first = (agent_dir / ".env.example").read_text()
    await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "fake-mcp"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    env_ex_second = (agent_dir / ".env.example").read_text()
    assert env_ex_first == env_ex_second


@pytest.mark.asyncio
async def test_attach_gcal_writes_setup_auth_py(tmp_path):
    """E3: mcp recipe with oauth_scopes -> setup_auth.py rendered + AGENT.md banner."""
    from agent_builder.tools.scaffold import scaffold_agent
    out = tmp_path / "output"
    out.mkdir()
    await scaffold_agent(
        {"agent_name": "cal-bot", "description": "x"},
        output_base=str(out),
    )
    # Overwrite tools.py + AGENT.md with minimal versions the attach path accepts.
    (out / "cal-bot" / "tools.py").write_text(
        'from claude_agent_sdk import tool, create_sdk_mcp_server\n'
        'TEST_MODE = False\n'
        'tools_server = create_sdk_mcp_server(name="agent-tools", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    (out / "cal-bot" / "AGENT.md").write_text("# Agent\n\nTest.\n", encoding="utf-8")

    result = await attach_recipe(
        {"agent_name": "cal-bot", "recipe_name": "google-calendar"},
        output_base=str(out),
        # Default recipes_root — uses the real bundled recipe.
    )
    assert result.get("is_error") is not True, result
    setup_py = out / "cal-bot" / "setup_auth.py"
    assert setup_py.exists()
    content = setup_py.read_text()
    assert "https://www.googleapis.com/auth/calendar" in content
    assert "{{scopes}}" not in content
    assert "{{client_secrets_env}}" not in content
    assert "{{token_path_env}}" not in content
    assert "{{recipe_name}}" not in content
    # Handoff banner appended to AGENT.md
    agent_md = (out / "cal-bot" / "AGENT.md").read_text()
    assert "First-run setup" in agent_md
    assert "google-calendar" in agent_md


@pytest.mark.asyncio
async def test_attach_second_poll_source_errors(poll_agent_dir):
    """Only one poll source per agent — second attach of a different
    poll_source recipe must fail with is_error."""
    from agent_builder.recipes.loader import default_recipes_root
    from agent_builder.manifest import Manifest, AttachedRecipe, save_manifest, load_manifest

    # Pretend another poll recipe was already attached by hand-editing the manifest.
    manifest_path = poll_agent_dir / MANIFEST_FILENAME
    m = load_manifest(manifest_path, agent_name="poll-agent")
    m.poll_source = "some-other-poll-recipe"
    save_manifest(manifest_path, m)

    result = await attach_recipe(
        {"agent_name": "poll-agent", "recipe_name": "telegram-poll"},
        output_base=str(poll_agent_dir.parent),
        recipes_root=default_recipes_root(),
    )
    assert result["is_error"] is True
    assert "poll source" in result["content"][0]["text"].lower()
