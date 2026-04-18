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

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder.tools.registry import DEFAULT_REGISTRY
from agent_builder.tools.scaffold import _validate_agent_name
from agent_builder.tools.write_tools import TOOLS_HEADER

IDENTITY_FILE_MAP = {
    "agent_md": "AGENT.md",
    "soul_md": "SOUL.md",
    "memory_md": "MEMORY.md",
    "user_md": "USER.md",
}


def _bump_registry_updated_at(agent_name: str, registry_file: str) -> None:
    """Advance the registry entry's updated_at to today.

    We touch the registry from edit_agent so that 'last modified' tracks
    real edits (not just initial scaffold). Silent no-op if the agent isn't
    registered or the registry file is missing/corrupt — edit_agent shouldn't
    fail a user edit just because the registry is in an odd state.
    """
    path = Path(registry_file)
    if not path.exists():
        return
    try:
        agents = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(agents, list):
        return
    for entry in agents:
        if isinstance(entry, dict) and entry.get("name") == agent_name:
            entry["updated_at"] = date.today().isoformat()
            try:
                path.write_text(json.dumps(agents, indent=2), encoding="utf-8")
            except OSError:
                return
            return


class BackupCollisionError(RuntimeError):
    """Raised when a `.bak-<stamp>` sibling already exists (sub-second repeat).

    Aborts the edit rather than silently clobbering the backup and losing the
    original. Matches rollback's collision semantics.
    """


def _backup(target: Path) -> Path | None:
    """Write target.with_suffix(...bak-<timestamp>) if target exists.

    Raises BackupCollisionError on sub-second collision (same-stamp sibling
    already present) — safer than overwriting the existing backup.
    """
    if not target.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target.with_suffix(target.suffix + f".bak-{stamp}")
    if backup.exists():
        raise BackupCollisionError(str(backup))
    backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


async def edit_agent(
    args: dict[str, Any],
    output_base: str = "output",
    registry_file: str = DEFAULT_REGISTRY,
) -> dict[str, Any]:
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

    try:
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
    except BackupCollisionError as e:
        return {
            "content": [{"type": "text", "text": (
                f"Refusing to edit '{agent_name}' — backup path already exists: {e}. "
                f"Sub-second repeat edit detected. Wait a second and retry. "
                f"Partial edits before the collision: {applied or 'none'}."
            )}],
            "is_error": True,
        }

    # Successful edit — bump the registry's updated_at so 'last modified'
    # tracks real changes. Silent no-op if this agent isn't registered.
    _bump_registry_updated_at(agent_name, registry_file)

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
