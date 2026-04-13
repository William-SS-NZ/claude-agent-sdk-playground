"""test_agent tool — run generated agent in mock mode and verify it works."""

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    tool,
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
)
from agent_builder.utils import build_claude_md


def _set_test_mode(tools_py_path: Path, enabled: bool) -> None:
    """Flip TEST_MODE in a tools.py file."""
    content = tools_py_path.read_text(encoding="utf-8")
    if enabled:
        content = content.replace("TEST_MODE = False", "TEST_MODE = True")
    else:
        content = content.replace("TEST_MODE = True", "TEST_MODE = False")
    tools_py_path.write_text(content, encoding="utf-8")


def _load_tools_server(tools_py_path: Path) -> Any:
    """Dynamically import tools.py and return the tools_server object."""
    spec = importlib.util.spec_from_file_location("generated_tools", str(tools_py_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {tools_py_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generated_tools"] = module
    spec.loader.exec_module(module)
    return module.tools_server


@tool(
    "test_agent",
    "Run a generated agent in mock mode (TEST_MODE=True) to verify it works. "
    "Sends test prompts and reports pass/fail for each.",
    {"agent_name": str, "test_prompts": list},
)
async def test_agent(args: dict[str, Any], output_base: str = "output") -> dict[str, Any]:
    agent_name = args["agent_name"]
    test_prompts: list[str] = args["test_prompts"]
    agent_dir = Path(output_base) / agent_name
    tools_py_path = agent_dir / "tools.py"

    if not tools_py_path.exists():
        return {
            "content": [{"type": "text", "text": f"tools.py not found at {tools_py_path}"}],
            "is_error": True,
        }

    # Build CLAUDE.md from identity files
    identity_dir = str(agent_dir)
    try:
        build_claude_md(source_dir=identity_dir, output_dir=identity_dir)
    except FileNotFoundError as e:
        return {
            "content": [{"type": "text", "text": f"Identity file missing: {e}"}],
            "is_error": True,
        }

    # Flip TEST_MODE and load tools
    _set_test_mode(tools_py_path, enabled=True)
    try:
        try:
            tools_server = _load_tools_server(tools_py_path)
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Failed to import tools.py:\n{traceback.format_exc()}",
                    }
                ],
                "is_error": True,
            }

        options = ClaudeAgentOptions(
            setting_sources=["project"],
            cwd=str(agent_dir),
            mcp_servers={"agent_tools": tools_server},
            allowed_tools=["mcp__agent_tools__*"],
            max_turns=5,
        )

        results: list[dict[str, str]] = []
        for prompt in test_prompts:
            try:
                status = "fail"
                error_detail = ""
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, AssistantMessage) and message.error:
                        error_detail = str(message.error)
                    if isinstance(message, ResultMessage):
                        if message.subtype == "success":
                            status = "pass"
                        else:
                            error_detail = f"subtype={message.subtype}"
                results.append({"prompt": prompt, "status": status, "error": error_detail})
            except Exception as e:
                results.append({"prompt": prompt, "status": "fail", "error": str(e)})

    finally:
        # Always reset TEST_MODE
        _set_test_mode(tools_py_path, enabled=False)
        # Clean up sys.modules
        sys.modules.pop("generated_tools", None)

    passed = sum(1 for r in results if r["status"] == "pass")
    total = len(results)
    lines = [f"Test results for '{agent_name}': {passed}/{total} passed\n"]
    for r in results:
        icon = "PASS" if r["status"] == "pass" else "FAIL"
        line = f"  [{icon}] {r['prompt']}"
        if r["error"]:
            line += f"\n         Error: {r['error']}"
        lines.append(line)

    all_passed = passed == total
    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "is_error": not all_passed,
    }
