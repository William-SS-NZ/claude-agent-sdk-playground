from agent_builder.utils import format_tool_call


def test_bash_shows_command():
    out = format_tool_call("Bash", {"command": "ls -la"})
    assert "Bash" in out and "command=ls -la" in out


def test_read_shows_file_path():
    out = format_tool_call("Read", {"file_path": "/tmp/foo.py"})
    assert "file_path=/tmp/foo.py" in out


def test_truncates_long_command():
    long_cmd = "echo " + "x" * 200
    out = format_tool_call("Bash", {"command": long_cmd})
    assert out.endswith("...")
    assert len(out) < 130


def test_collapses_whitespace():
    out = format_tool_call("Bash", {"command": "foo\n\nbar   baz"})
    assert "foo bar baz" in out
    assert "\n" not in out


def test_mcp_prefix_stripped():
    out = format_tool_call("mcp__builder_tools__scaffold_agent", {"agent_name": "hacker-ui"})
    assert out.startswith("  [Tool: scaffold_agent]")
    assert "mcp__" not in out


def test_mcp_picks_known_keys_in_order():
    out = format_tool_call("mcp__agent_tools__open_page", {"url": "https://example.com", "extra": "x"})
    assert "url=https://example.com" in out


def test_falls_back_to_first_scalar_for_unknown_tool():
    out = format_tool_call("Unknown", {"nonscalar": [1, 2], "something": "hello"})
    assert "something=hello" in out


def test_empty_input_returns_bare_name():
    out = format_tool_call("Bash", {})
    assert out.strip() == "[Tool: Bash]"
