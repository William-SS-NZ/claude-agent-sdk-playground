"""write_identity tool — writes AGENT.md, SOUL.md, MEMORY.md, USER.md."""

from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

FILE_MAP = {
    "agent_md": "AGENT.md",
    "soul_md": "SOUL.md",
    "memory_md": "MEMORY.md",
    "user_md": "USER.md",
}


async def write_identity(args: dict[str, Any], output_base: str = "output") -> dict[str, Any]:
    """Write identity files for a generated agent.

    Args:
        args: Dict with keys agent_name, agent_md, soul_md, memory_md, user_md.
        output_base: Base directory containing agent subdirectories.

    Returns:
        MCP-style result dict with content list, or is_error on failure.
    """
    agent_name = args["agent_name"]
    agent_dir = Path(output_base) / agent_name

    if not agent_dir.exists():
        return {
            "content": [{"type": "text", "text": f"Agent directory not found: {agent_dir}"}],
            "is_error": True,
        }

    written: list[str] = []
    total_chars = 0

    for key, filename in FILE_MAP.items():
        content = args.get(key)
        if content is None:
            continue
        (agent_dir / filename).write_text(content, encoding="utf-8")
        written.append(filename)
        total_chars += len(content)

    return {
        "content": [
            {
                "type": "text",
                "text": f"Wrote identity files for '{agent_name}': {', '.join(written)} ({total_chars} chars total)",
            }
        ]
    }


# MCP tool registration — wraps the async function for use with create_sdk_mcp_server()
write_identity_tool = tool(
    "write_identity",
    "Write identity files (AGENT.md, SOUL.md, MEMORY.md, USER.md) for a generated agent",
    {
        "agent_name": str,
        "agent_md": str,
        "soul_md": str,
        "memory_md": str,
    },
)(write_identity)
