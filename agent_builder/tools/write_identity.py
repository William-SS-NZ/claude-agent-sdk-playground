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

# Windows spawns the claude CLI with the system prompt inline. CreateProcessW's
# lpCommandLine caps at 8191 chars, so leave headroom below that for the
# combined AGENT.md + SOUL.md + MEMORY.md + USER.md content that becomes the
# system prompt via setting_sources=["project"].
IDENTITY_SOFT_LIMIT = 6000


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
    per_file_sizes: list[tuple[str, int]] = []

    for key, filename in FILE_MAP.items():
        content = args.get(key)
        if content is None:
            continue
        (agent_dir / filename).write_text(content, encoding="utf-8")
        written.append(filename)
        total_chars += len(content)
        per_file_sizes.append((filename, len(content)))

    size_breakdown = ", ".join(f"{n}={s}" for n, s in per_file_sizes)
    summary = (
        f"Wrote identity files for '{agent_name}': {', '.join(written)} "
        f"({total_chars} chars total — {size_breakdown})"
    )
    if total_chars > IDENTITY_SOFT_LIMIT:
        summary += (
            f"\n[WARNING] Total identity content ({total_chars} chars) exceeds the "
            f"{IDENTITY_SOFT_LIMIT}-char soft limit. On Windows the claude CLI's "
            "8191-char command-line cap may cause subprocess failures. "
            "Consider trimming AGENT.md/SOUL.md/MEMORY.md or splitting detail "
            "into a reference doc the agent reads on demand."
        )

    return {"content": [{"type": "text", "text": summary}]}


# MCP tool registration — wraps the async function for use with create_sdk_mcp_server()
write_identity_tool = tool(
    "write_identity",
    "Write identity files (AGENT.md, SOUL.md, MEMORY.md, USER.md) for a generated agent",
    {
        "agent_name": str,
        "agent_md": str,
        "soul_md": str,
        "memory_md": str,
        "user_md": str,
    },
)(write_identity)
