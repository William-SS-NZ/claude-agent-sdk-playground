"""End-to-end: scaffold + attach both shipped recipes and validate the file surface."""

from pathlib import Path

import pytest

from agent_builder.tools.attach_recipe import attach_recipe
from agent_builder.tools.scaffold import scaffold_agent


@pytest.mark.asyncio
async def test_build_tg_gcal_agent_end_to_end(tmp_path):
    out = tmp_path / "output"
    out.mkdir()

    result = await scaffold_agent(
        {"agent_name": "tg-gcal", "description": "Telegram to Google Calendar.", "mode": "poll"},
        output_base=str(out),
    )
    assert result.get("is_error") is not True, result

    # Minimal tools.py + AGENT.md — real builds get these from write_tools / write_identity.
    (out / "tg-gcal" / "tools.py").write_text(
        'from claude_agent_sdk import tool, create_sdk_mcp_server\n'
        'TEST_MODE = False\n'
        'tools_server = create_sdk_mcp_server(name="agent-tools", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    (out / "tg-gcal" / "AGENT.md").write_text("# Agent\n\nTest agent.\n", encoding="utf-8")

    for recipe in ("telegram-poll", "google-calendar"):
        result = await attach_recipe(
            {"agent_name": "tg-gcal", "recipe_name": recipe},
            output_base=str(out),
        )
        assert result.get("is_error") is not True, (recipe, result)

    agent_dir = out / "tg-gcal"
    assert (agent_dir / "setup_auth.py").exists()

    agent_py = (agent_dir / "agent.py").read_text()
    assert "_stub_poll_source()" not in agent_py
    assert '"google-calendar"' in agent_py
    assert "RECIPE_PINS" in agent_py
    assert '"telegram-poll"' in agent_py

    env_ex = (agent_dir / ".env.example").read_text()
    assert "TELEGRAM_BOT_TOKEN" in env_ex
    assert "GOOGLE_OAUTH_CLIENT_SECRETS" in env_ex

    agent_md = (agent_dir / "AGENT.md").read_text()
    assert "First-run setup" in agent_md
