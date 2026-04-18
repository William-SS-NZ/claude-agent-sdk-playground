"""edit_agent tool — update an existing agent's identity files or tools.py in place.

Unlike `write_identity` + `write_tools` which are meant for the generation
flow and blindly write whatever is passed, `edit_agent` is meant for the
iterative "tweak an already-built agent" case. It:

- Validates the agent directory exists before touching anything
- Only writes fields that are supplied (missing = unchanged)
- Writes a `.bak-<timestamp>` backup of every file it modifies
- Prepends the canonical tools.py header when tools_code is supplied, so
  callers can pass just the tool-function bodies (same contract as
  write_tools)
- Does NOT touch agent.py, .env.example, or .gitignore — those are fixed
  at scaffold time. If you need those changed, re-scaffold or hand-edit.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder.tools.scaffold import _validate_agent_name
from agent_builder.tools.write_tools import TOOLS_HEADER

IDENTITY_FILE_MAP = {
    "agent_md": "AGENT.md",
    "soul_md": "SOUL.md",
    "memory_md": "MEMORY.md",
    "user_md": "USER.md",
}


def _backup(target: Path) -> Path | None:
    """Write target.with_suffix(...bak-<timestamp>) if target exists."""
    if not target.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target.with_suffix(target.suffix + f".bak-{stamp}")
    backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


async def edit_agent(args: dict[str, Any], output_base: str = "output") -> dict[str, Any]:
    agent_name = args["agent_name"]

    error = _validate_agent_name(agent_name, output_base)
    if error:
        return {"content": [{"type": "text", "text": error}], "is_error": True}

    agent_dir = Path(output_base) / agent_name
    if not agent_dir.exists():
        return {
            "content": [{"type": "text", "text": f"Agent directory not found: {agent_dir}. Use scaffold_agent first."}],
            "is_error": True,
        }

    # Collect requested changes
    identity_changes: list[tuple[str, str]] = []
    for key, filename in IDENTITY_FILE_MAP.items():
        content = args.get(key)
        if content is not None:
            identity_changes.append((filename, content))

    tools_code = args.get("tools_code")

    if not identity_changes and tools_code is None:
        return {
            "content": [{"type": "text", "text": "Nothing to change — supply at least one of agent_md, soul_md, memory_md, user_md, or tools_code."}],
            "is_error": True,
        }

    applied: list[str] = []
    backups: list[str] = []

    for filename, content in identity_changes:
        target = agent_dir / filename
        backup = _backup(target)
        if backup:
            backups.append(backup.name)
        target.write_text(content, encoding="utf-8")
        applied.append(f"{filename} ({len(content)} chars)")

    if tools_code is not None:
        target = agent_dir / "tools.py"
        backup = _backup(target)
        if backup:
            backups.append(backup.name)
        full_content = TOOLS_HEADER + "\n" + tools_code
        target.write_text(full_content, encoding="utf-8")
        applied.append(f"tools.py ({len(full_content)} chars)")

    lines = [f"Updated '{agent_name}': {len(applied)} file(s) changed."]
    for line in applied:
        lines.append(f"  - {line}")
    if backups:
        lines.append(f"Backups: {', '.join(backups)}")
    lines.append("Restart the agent to pick up the changes.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


edit_agent_tool = tool(
    "edit_agent",
    "Update an existing generated agent in place. Any of agent_md, soul_md, "
    "memory_md, user_md, or tools_code that is supplied replaces that file; "
    "missing fields leave the existing content untouched. Each overwritten "
    "file gets a .bak-<timestamp> backup first. tools_code must be just the "
    "tool-function bodies (same contract as write_tools — the canonical "
    "TOOLS_HEADER is prepended automatically). The agent directory must "
    "already exist; use scaffold_agent for new agents.",
    {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string"},
            "agent_md": {"type": "string"},
            "soul_md": {"type": "string"},
            "memory_md": {"type": "string"},
            "user_md": {"type": "string"},
            "tools_code": {"type": "string"},
        },
        "required": ["agent_name"],
    },
)(edit_agent)
