import pytest
from pathlib import Path
from agent_builder.tools.write_tools import write_tools

SAMPLE_TOOLS_CODE = '''
@tool("greet", "Greet a user", {"name": str})
async def greet(args: dict[str, Any]) -> dict[str, Any]:
    if TEST_MODE:
        return {"content": [{"type": "text", "text": "Mock: Hello, friend!"}]}
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}


tools_server = create_sdk_mcp_server(name="agent-tools", version="1.0.0", tools=[greet])
'''


@pytest.mark.asyncio
async def test_write_tools_creates_file(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    result = await write_tools(
        {"agent_name": "test-agent", "tools_code": SAMPLE_TOOLS_CODE},
        output_base=str(tmp_path),
    )

    tools_py = agent_dir / "tools.py"
    assert tools_py.exists()
    content = tools_py.read_text(encoding="utf-8")
    assert "TEST_MODE = False" in content
    assert "from claude_agent_sdk import" in content
    assert "from typing import Any" in content
    assert "async def greet" in content
    assert "tools_server" in content
    assert "is_error" not in result


@pytest.mark.asyncio
async def test_write_tools_header_before_code(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    await write_tools(
        {"agent_name": "test-agent", "tools_code": SAMPLE_TOOLS_CODE},
        output_base=str(tmp_path),
    )

    content = (agent_dir / "tools.py").read_text(encoding="utf-8")
    header_pos = content.index("TEST_MODE = False")
    code_pos = content.index("async def greet")
    assert header_pos < code_pos


@pytest.mark.asyncio
async def test_write_tools_errors_on_missing_dir(tmp_path: Path):
    result = await write_tools(
        {"agent_name": "nonexistent", "tools_code": SAMPLE_TOOLS_CODE},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True
