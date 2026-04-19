"""Tests ensuring the poll-mode template has the expected placeholder set."""

from pathlib import Path


TEMPLATES_DIR = Path("agent_builder") / "templates"

EXPECTED_IN_POLL = {
    "{{agent_name}}",
    "{{agent_description}}",
    "{{builder_version}}",
    "{{recipe_pins_block}}",
    "{{tools_list}}",
    "{{allowed_tools_list}}",
    "{{permission_mode}}",
    "{{max_turns}}",
    "{{max_budget_usd}}",
    "{{poll_source_import}}",      # poll-only
    "{{poll_source_expr}}",        # poll-only
}


def test_poll_template_has_all_placeholders():
    content = (TEMPLATES_DIR / "agent_poll.py.tmpl").read_text(encoding="utf-8")
    missing = [p for p in EXPECTED_IN_POLL if p not in content]
    assert not missing, f"poll template missing placeholders: {missing}"


def test_poll_template_no_stdin_loop():
    content = (TEMPLATES_DIR / "agent_poll.py.tmpl").read_text(encoding="utf-8")
    assert 'input("> ")' not in content
    assert "asyncio.to_thread(input" not in content
