"""Verify the agent_main.py template auto-loads .env on startup."""

import ast
from pathlib import Path

import pytest

from agent_builder.tools.scaffold import scaffold_agent, TEMPLATES_DIR


def _render_template() -> str:
    """Render agent_main.py.tmpl with representative placeholder values,
    matching the substitution dance in scaffold_agent."""
    template = (TEMPLATES_DIR / "agent_main.py.tmpl").read_text(encoding="utf-8")
    return (
        template
        .replace("{{agent_name}}", "dotenv-test")
        .replace("{{tools_list}}", repr(["Read", "Edit"]))
        .replace("{{allowed_tools_list}}", repr(["Read", "Edit", "mcp__agent_tools__foo"]))
        .replace("{{permission_mode}}", "acceptEdits")
        .replace("{{max_turns}}", "25")
        .replace("{{max_budget_usd}}", "1.00")
    )


def test_rendered_template_imports_load_dotenv():
    rendered = _render_template()
    assert "load_dotenv" in rendered, "expected load_dotenv in rendered agent source"
    assert "from dotenv import load_dotenv" in rendered


def test_rendered_template_is_valid_python():
    rendered = _render_template()
    # Must parse — guards against accidental syntax breakage in the template.
    ast.parse(rendered)


def test_rendered_template_calls_load_dotenv_on_agent_dir():
    rendered = _render_template()
    # The .env should be loaded from next to agent.py (AGENT_DIR / ".env").
    assert 'load_dotenv(AGENT_DIR / ".env")' in rendered


def test_rendered_template_guards_missing_dotenv_import():
    """Generated agents must not hard-crash if python-dotenv is uninstalled —
    the import has to sit inside a try/except so load_dotenv falls back to a no-op."""
    rendered = _render_template()
    tree = ast.parse(rendered)

    found_guarded_import = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for child in node.body:
            if isinstance(child, ast.ImportFrom) and child.module == "dotenv":
                if any(alias.name == "load_dotenv" for alias in child.names):
                    found_guarded_import = True
                    break
        if found_guarded_import:
            break

    assert found_guarded_import, (
        "expected `from dotenv import load_dotenv` wrapped in a try/except "
        "so missing python-dotenv does not crash the generated agent"
    )


@pytest.mark.asyncio
async def test_scaffolded_agent_py_loads_dotenv(tmp_path: Path):
    """End-to-end: scaffold a real agent and check its agent.py wires up dotenv."""
    await scaffold_agent(
        {"agent_name": "dotenv-e2e", "description": "dotenv check"},
        output_base=str(tmp_path),
    )
    agent_py = (tmp_path / "dotenv-e2e" / "agent.py").read_text(encoding="utf-8")
    assert "from dotenv import load_dotenv" in agent_py
    assert 'load_dotenv(AGENT_DIR / ".env")' in agent_py
    # Confirm it still parses as valid Python post-substitution.
    ast.parse(agent_py)
