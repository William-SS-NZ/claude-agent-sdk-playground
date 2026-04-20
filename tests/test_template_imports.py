"""Tests that generated agents import shared utilities from agent_builder.utils.

Prior to v0.9, `Spinner`, `format_tool_call`, and `build_claude_md` were each
inlined into the generated agent's `agent.py` by copy-pasting the bodies
verbatim from the template. Every iteration on those utilities had to be
mirrored into the template — which drifted multiple times and cost real tests
to catch the drift.

R6 (v0.9) deduped these to live only in `agent_builder/utils.py`. Generated
agents now `from agent_builder.utils import ...` instead of carrying a copy.

These tests guard against regression: scaffold a throwaway agent, confirm the
generated agent.py imports from `agent_builder.utils`, confirm it does NOT
re-inline `class Spinner`, and confirm the rendered file is still valid Python.
"""

import ast
import asyncio
from pathlib import Path

from agent_builder.tools.scaffold import scaffold_agent


def _scaffold(tmp_path: Path, name: str = "tmpl-import-test", **overrides) -> Path:
    out = tmp_path / "output"
    out.mkdir()
    args = {
        "agent_name": name,
        "description": "template-import test",
        "tools_list": ["Read"],
        "allowed_tools_list": ["Read"],
        "permission_mode": "acceptEdits",
    }
    args.update(overrides)
    result = asyncio.run(scaffold_agent(args, output_base=str(out)))
    assert not result.get("is_error"), result
    return out / name / "agent.py"


def test_cli_template_imports_from_agent_builder_utils(tmp_path: Path) -> None:
    agent_py = _scaffold(tmp_path, name="cli-import")
    source = agent_py.read_text(encoding="utf-8")

    assert "from agent_builder.utils import" in source
    assert "Spinner" in source  # imported name is still present
    assert "format_tool_call" in source
    assert "build_claude_md" in source


def test_cli_template_has_no_inlined_spinner_class(tmp_path: Path) -> None:
    agent_py = _scaffold(tmp_path, name="cli-no-inline")
    source = agent_py.read_text(encoding="utf-8")

    # If Spinner is imported, it must NOT also be declared in the file.
    assert "class Spinner" not in source
    # Same for the helper ctx and truncate — they live in utils now.
    assert "class _NullCtx" not in source
    assert "def _truncate(" not in source
    # And the IDENTITY_FILES / CLAUDE_MD_HEADER module-level constants must not
    # be redeclared (they live in utils alongside build_claude_md).
    assert "IDENTITY_FILES = [" not in source
    assert "CLAUDE_MD_HEADER =" not in source


def test_cli_template_agent_py_parses_as_valid_python(tmp_path: Path) -> None:
    agent_py = _scaffold(tmp_path, name="cli-ast")
    source = agent_py.read_text(encoding="utf-8")

    # ast.parse will raise SyntaxError if the template substitution produced
    # broken Python. This guards against accidental de-indentation or stray
    # placeholder leftovers from the strip.
    ast.parse(source)


def test_poll_template_imports_from_agent_builder_utils(tmp_path: Path) -> None:
    agent_py = _scaffold(tmp_path, name="poll-import", mode="poll", cli_mode=False)
    source = agent_py.read_text(encoding="utf-8")

    assert "from agent_builder.utils import" in source
    assert "Spinner" in source
    assert "format_tool_call" in source
    assert "build_claude_md" in source


def test_poll_template_has_no_inlined_spinner_class(tmp_path: Path) -> None:
    agent_py = _scaffold(tmp_path, name="poll-no-inline", mode="poll", cli_mode=False)
    source = agent_py.read_text(encoding="utf-8")

    assert "class Spinner" not in source
    assert "class _NullCtx" not in source
    assert "def _truncate(" not in source
    assert "IDENTITY_FILES = [" not in source
    assert "CLAUDE_MD_HEADER =" not in source


def test_poll_template_agent_py_parses_as_valid_python(tmp_path: Path) -> None:
    agent_py = _scaffold(tmp_path, name="poll-ast", mode="poll", cli_mode=False)
    source = agent_py.read_text(encoding="utf-8")

    ast.parse(source)
