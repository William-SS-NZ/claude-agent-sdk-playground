"""remove_agent tool — safely delete a generated agent directory and its registry entry."""

import json
import shutil
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder.paths import validate_relative_to_base
from agent_builder.tools.scaffold import _validate_agent_name

DEFAULT_REGISTRY = str(Path(__file__).parent.parent / "registry" / "agents.json")


async def remove_agent(
    args: dict[str, Any],
    output_base: str = "output",
    registry_file: str = DEFAULT_REGISTRY,
) -> dict[str, Any]:
    """Delete an agent's output directory and drop its registry entry.

    Safety:
    - Agent name is validated with the same rules as scaffold (no '..', '/', '\\').
    - The resolved target directory must live inside output_base — anything resolving
      outside is rejected.
    - Refuses to delete output_base itself.
    """
    agent_name = args.get("agent_name", "")

    error = _validate_agent_name(agent_name, output_base)
    if error:
        return {"content": [{"type": "text", "text": error}], "is_error": True}

    base = Path(output_base).resolve()

    # Shared containment check — defence in depth on top of the slug/name
    # validation above. Rejects anything that resolves outside output_base.
    target, err = validate_relative_to_base(
        str(base / agent_name),
        [base],
    )
    if err is not None or target is None:
        return {
            "content": [{"type": "text", "text": f"Target escapes output base: {err}"}],
            "is_error": True,
        }

    if target == base:
        return {
            "content": [{"type": "text", "text": "Refusing to delete the output directory itself."}],
            "is_error": True,
        }

    removed_dir = False
    if target.exists() and target.is_dir():
        shutil.rmtree(target)
        removed_dir = True

    # Drop from registry
    reg_path = Path(registry_file)
    removed_from_registry = False
    if reg_path.exists():
        agents: list[dict[str, Any]] = json.loads(reg_path.read_text(encoding="utf-8"))
        remaining = [a for a in agents if a.get("name") != agent_name]
        if len(remaining) != len(agents):
            reg_path.write_text(json.dumps(remaining, indent=2), encoding="utf-8")
            removed_from_registry = True

    if not removed_dir and not removed_from_registry:
        return {
            "content": [{"type": "text", "text": f"Agent '{agent_name}' has no directory and no registry entry — nothing to remove."}],
            "is_error": True,
        }

    parts = []
    if removed_dir:
        parts.append(f"deleted {target}")
    if removed_from_registry:
        parts.append("removed registry entry")
    return {"content": [{"type": "text", "text": f"Removed agent '{agent_name}': {', '.join(parts)}."}]}


remove_agent_tool = tool(
    "remove_agent",
    "Safely delete a generated agent: removes output/<agent_name>/ and drops its registry entry. "
    "Rejects path-traversal attempts and refuses to touch anything outside output_base.",
    {"agent_name": str},
)(remove_agent)
