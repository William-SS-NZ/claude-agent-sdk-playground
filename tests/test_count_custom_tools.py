"""Tests for _count_custom_tools_from_source.

The counter parses tools.py via ast and counts the elements of the
tools=[...] keyword arg passed to create_sdk_mcp_server(...). It must be
robust to:
 - the canonical empty stub (EMPTY_TOOLS_BODY) -> 0
 - a single tool registered             -> 1
 - multiple tools registered            -> N
 - malformed / unparseable source       -> 0 (fail soft)
 - missing the create_sdk_mcp_server call -> 0
"""

from pathlib import Path

import pytest

from agent_builder.tools.test_agent import _count_custom_tools_from_source
from agent_builder.tools.write_tools import EMPTY_TOOLS_BODY, TOOLS_HEADER


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "tools.py"
    p.write_text(TOOLS_HEADER + "\n" + body, encoding="utf-8")
    return p


def test_empty_stub_returns_zero(tmp_path: Path):
    """EMPTY_TOOLS_BODY — canonical no-tools shape — must count as 0."""
    tools_py = _write(tmp_path, EMPTY_TOOLS_BODY)
    assert _count_custom_tools_from_source(tools_py) == 0


def test_single_tool_returns_one(tmp_path: Path):
    body = '''\
@tool("do_thing", "Does a thing.", {"x": str})
async def do_thing(args):
    return {"content": [{"type": "text", "text": "ok"}]}

tools_server = create_sdk_mcp_server(
    name="agent-tools",
    version="1.0.0",
    tools=[do_thing],
)
'''
    tools_py = _write(tmp_path, body)
    assert _count_custom_tools_from_source(tools_py) == 1


def test_multiple_tools_returns_n(tmp_path: Path):
    body = '''\
@tool("a", "A.", {})
async def a(args):
    return {"content": [{"type": "text", "text": "a"}]}

@tool("b", "B.", {})
async def b(args):
    return {"content": [{"type": "text", "text": "b"}]}

@tool("c", "C.", {})
async def c(args):
    return {"content": [{"type": "text", "text": "c"}]}

tools_server = create_sdk_mcp_server(
    name="agent-tools",
    version="1.0.0",
    tools=[a, b, c],
)
'''
    tools_py = _write(tmp_path, body)
    assert _count_custom_tools_from_source(tools_py) == 3


def test_malformed_source_returns_zero(tmp_path: Path):
    """A SyntaxError in tools.py must fail soft -> 0, not raise."""
    p = tmp_path / "tools.py"
    p.write_text("this is not valid python ::: def !!!", encoding="utf-8")
    assert _count_custom_tools_from_source(p) == 0


def test_missing_create_call_returns_zero(tmp_path: Path):
    """Valid python with no create_sdk_mcp_server call -> 0."""
    p = tmp_path / "tools.py"
    p.write_text("x = 1\ny = [1, 2, 3]\n", encoding="utf-8")
    assert _count_custom_tools_from_source(p) == 0


def test_nonexistent_file_returns_zero(tmp_path: Path):
    """Missing file must not raise — counter treats it as unknown/zero."""
    missing = tmp_path / "does_not_exist.py"
    assert _count_custom_tools_from_source(missing) == 0


def test_tools_kwarg_not_literal_returns_zero(tmp_path: Path):
    """If tools= is a variable (not a literal list/tuple), we can't count it."""
    body = '''\
_all = []
tools_server = create_sdk_mcp_server(
    name="agent-tools",
    version="1.0.0",
    tools=_all,
)
'''
    tools_py = _write(tmp_path, body)
    assert _count_custom_tools_from_source(tools_py) == 0
