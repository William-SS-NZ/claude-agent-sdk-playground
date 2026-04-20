"""Tests for test_agent's poll mode — subprocess-driven synthetic-message run."""

import json
import os
import sys
from pathlib import Path

import pytest

from agent_builder.tools.scaffold import scaffold_agent
from agent_builder.tools.test_agent import test_agent as run_test_agent


async def _scaffold_poll_agent(out: Path, name: str = "poll-t") -> Path:
    """Scaffold a minimal poll-mode agent with identity + trivial tools.py."""
    result = await scaffold_agent(
        {"agent_name": name, "description": "poll agent under test", "mode": "poll"},
        output_base=str(out),
    )
    assert result.get("is_error") is not True, result

    agent_dir = out / name
    # Minimal tools.py that registers an empty tools_server; test_agent expects
    # the `tools_server` symbol at module scope.
    (agent_dir / "tools.py").write_text(
        "from claude_agent_sdk import tool, create_sdk_mcp_server\n"
        "TEST_MODE = False\n"
        "tools_server = create_sdk_mcp_server(name=\"agent-tools\", version=\"0.1.0\", tools=[])\n",
        encoding="utf-8",
    )
    for md, body in (
        ("AGENT.md", "# Agent\nTest agent."),
        ("SOUL.md", "# Soul\nHelpful."),
        ("MEMORY.md", "# Memory\nNothing yet."),
    ):
        (agent_dir / md).write_text(body, encoding="utf-8")
    return agent_dir


@pytest.mark.asyncio
async def test_test_agent_poll_mode_processes_synthetic_messages(tmp_path):
    """Poll mode runs `python agent.py` as a subprocess against a fake
    poll-source that yields the supplied messages. After messages drain,
    the stub signals end-of-stream and the subprocess exits cleanly."""
    out = tmp_path / "output"
    out.mkdir()
    agent_dir = await _scaffold_poll_agent(out, name="poll-t")

    messages = [
        {"sender_id": 1, "chat_id": 1, "text": "hello"},
        {"sender_id": 1, "chat_id": 1, "text": "goodbye"},
    ]
    result = await run_test_agent(
        {
            "agent_name": "poll-t",
            "mode": "poll",
            "messages": messages,
            "test_prompts": [],  # unused in poll mode, accepted for shape compat
        },
        output_base=str(out),
    )
    assert result.get("is_error") is not True, result["content"][0]["text"]
    text = result["content"][0]["text"]
    # Surfaced message count tells us every synthetic Incoming was iterated.
    assert "2" in text
    assert "poll" in text.lower()

    # After the run, agent.py has been restored (no stub import lingering).
    agent_py = (agent_dir / "agent.py").read_text(encoding="utf-8")
    assert "_poll_source_test_stub" not in agent_py
    # And the stub file is gone.
    assert not (agent_dir / "_poll_source_test_stub.py").exists()


@pytest.mark.asyncio
async def test_test_agent_poll_mode_missing_messages_errors(tmp_path):
    """Poll mode without messages returns is_error."""
    out = tmp_path / "output"
    out.mkdir()
    await _scaffold_poll_agent(out, name="poll-m")

    result = await run_test_agent(
        {
            "agent_name": "poll-m",
            "mode": "poll",
            "test_prompts": [],
        },
        output_base=str(out),
    )
    assert result["is_error"] is True
    assert "message" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_test_agent_cli_mode_still_default(tmp_path):
    """No mode param (or mode='cli') takes the original path — regression check."""
    # This test is here to document that test_agent's original callers (all of
    # which pass test_prompts) still work. We don't actually run the CLI path
    # (that requires a real model call); we just assert that the absence of
    # mode='poll' doesn't accidentally trigger the poll-mode branch.
    out = tmp_path / "output"
    out.mkdir()
    agent_dir = await _scaffold_poll_agent(out, name="cli-c")

    # Missing test_prompts with mode='cli' (default) — old behavior: requires
    # test_prompts; we check the shape is unchanged.
    result = await run_test_agent(
        {"agent_name": "cli-c", "test_prompts": []},
        output_base=str(out),
    )
    # Empty test_prompts produces 0/0 passed — not an error.
    text = result["content"][0]["text"]
    assert "0/0" in text or "passed" in text
