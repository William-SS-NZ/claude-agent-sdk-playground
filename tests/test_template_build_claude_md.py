"""Tests for the inlined build_claude_md in agent_main.py.tmpl.

The template carries its own copy of build_claude_md so scaffolded agents can
run standalone. That copy drifted once before (silently skipping missing
required files instead of raising). These tests import the template as a real
module and exercise its build_claude_md directly to catch any future drift.
"""

import importlib.util
import sys
from pathlib import Path

import pytest


TEMPLATE_PATH = (
    Path(__file__).parent.parent / "agent_builder" / "templates" / "agent_main.py.tmpl"
)


def _render_template(agent_dir: Path, agent_name: str = "tmpl-test") -> Path:
    """Substitute placeholders and write the template as agent.py in agent_dir."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = (
        template
        .replace("{{agent_name}}", agent_name)
        .replace("{{agent_description}}", f"{agent_name} test")
        .replace("{{tools_list}}", repr(["Read"]))
        .replace("{{allowed_tools_list}}", repr(["Read"]))
        .replace("{{permission_mode}}", "acceptEdits")
        .replace("{{max_turns}}", "25")
        .replace("{{max_budget_usd}}", "1.00")
        .replace("{{cli_args_block}}", "")
        .replace("{{cli_dispatch_block}}", "")
    )
    assert "{{" not in rendered, "unfilled template placeholders remain"
    agent_py = agent_dir / "agent.py"
    agent_py.write_text(rendered, encoding="utf-8")
    return agent_py


def _import_agent(agent_py: Path, module_name: str):
    """Import the rendered agent.py as a real module so its globals resolve."""
    spec = importlib.util.spec_from_file_location(module_name, agent_py)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so `from __main__` style references resolve if needed.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


@pytest.fixture
def rendered_agent(tmp_path: Path, request: pytest.FixtureRequest):
    """Render the template into tmp_path and import it. Cleans up sys.modules."""
    agent_py = _render_template(tmp_path)
    # Unique module name per test so re-imports don't collide.
    module_name = f"_tmpl_agent_{request.node.name}"
    module = _import_agent(agent_py, module_name)
    yield module, tmp_path
    sys.modules.pop(module_name, None)


def _seed_required_identity(agent_dir: Path) -> None:
    (agent_dir / "AGENT.md").write_text("# Agent\nYou are a template test agent.", encoding="utf-8")
    (agent_dir / "SOUL.md").write_text("# Soul\nBe helpful.", encoding="utf-8")
    (agent_dir / "MEMORY.md").write_text("# Memory\nSeed context.", encoding="utf-8")


def test_template_build_claude_md_writes_file_with_header(rendered_agent):
    module, agent_dir = rendered_agent
    _seed_required_identity(agent_dir)

    module.build_claude_md()

    claude_md = agent_dir / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in content


def test_template_build_claude_md_includes_required_sections(rendered_agent):
    module, agent_dir = rendered_agent
    _seed_required_identity(agent_dir)

    module.build_claude_md()

    content = (agent_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "You are a template test agent." in content
    assert "Be helpful." in content
    assert "Seed context." in content


def test_template_build_claude_md_includes_user_md_when_present(rendered_agent):
    module, agent_dir = rendered_agent
    _seed_required_identity(agent_dir)
    (agent_dir / "USER.md").write_text("# User\nName: William", encoding="utf-8")

    module.build_claude_md()

    content = (agent_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Name: William" in content


def test_template_build_claude_md_skips_missing_user_md(rendered_agent):
    module, agent_dir = rendered_agent
    _seed_required_identity(agent_dir)
    assert not (agent_dir / "USER.md").exists()

    # Must not raise.
    module.build_claude_md()

    content = (agent_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# User" not in content


def test_template_build_claude_md_raises_when_agent_md_missing(rendered_agent):
    """Regression: template used to silently skip missing required files.
    It must raise FileNotFoundError instead."""
    module, agent_dir = rendered_agent
    # Seed SOUL + MEMORY but deliberately omit AGENT.md.
    (agent_dir / "SOUL.md").write_text("# Soul\nBe helpful.", encoding="utf-8")
    (agent_dir / "MEMORY.md").write_text("# Memory\nSeed context.", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        module.build_claude_md()
