"""registry tool — track created agents in agents.json."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

DEFAULT_REGISTRY = str(Path(__file__).parent.parent / "registry" / "agents.json")

REQUIRED_AGENT_FILES = ("agent.py", "tools.py", "AGENT.md", "SOUL.md", "MEMORY.md")


def _verify_agent_complete(agent_name: str, output_base: str = "output") -> list[str]:
    """Return the list of required files missing from output/<agent_name>/.

    Empty list = build is complete. Used by `registry add` to refuse sealing
    a half-built agent (e.g. write_tools was skipped, so tools.py is missing
    and `python output/<name>/agent.py` would fail with ModuleNotFoundError
    on first run).
    """
    agent_dir = Path(output_base) / agent_name
    if not agent_dir.exists():
        return list(REQUIRED_AGENT_FILES)
    return [f for f in REQUIRED_AGENT_FILES if not (agent_dir / f).exists()]


async def registry(
    args: dict[str, Any],
    registry_file: str = DEFAULT_REGISTRY,
    output_base: str = "output",
    skip_validation: bool = False,
) -> dict[str, Any]:
    """Manage the agent registry (add, list, describe)."""
    path = Path(registry_file)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")

    agents: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    action = args["action"]

    if action == "add":
        agent_name = args.get("agent_name", "")
        # Refuse to seal a half-built agent — the model has skipped a Phase 4
        # tool. Returning is_error with the specific missing files lets the
        # model self-correct (call write_tools, write_identity, etc.) instead
        # of silently producing a broken agent. skip_validation is an internal
        # test-only escape hatch (not in the MCP schema, so the LLM can't pass it).
        missing = [] if skip_validation else _verify_agent_complete(agent_name, output_base)
        if missing:
            return {
                "content": [{"type": "text", "text": (
                    f"Refusing to register '{agent_name}' — incomplete build. "
                    f"Missing required files: {missing}. "
                    "Call the appropriate Phase 4 tool to create them, then re-run registry add."
                )}],
                "is_error": True,
            }
        today = date.today().isoformat()
        entry = {
            "name": agent_name,
            "description": args.get("description", ""),
            "tools": args.get("tools_list", []),
            "created": today,
            "updated_at": today,
            "path": f"output/{agent_name}/",
            "status": "active",
            "max_turns": args.get("max_turns"),
            "max_budget_usd": args.get("max_budget_usd"),
            "permission_mode": args.get("permission_mode"),
        }
        existing_idx = next((i for i, a in enumerate(agents) if a.get("name") == agent_name), None)
        if existing_idx is not None:
            prev = agents[existing_idx]
            # Preserve original creation date; refresh updated_at to today.
            entry["created"] = prev.get("created", entry["created"])
            entry["updated_at"] = today
            # Fall back to previous values for any SDK-config fields the caller
            # didn't pass this round, so partial updates don't wipe state.
            for key in ("max_turns", "max_budget_usd", "permission_mode"):
                if entry[key] is None:
                    entry[key] = prev.get(key)
            agents[existing_idx] = entry
            verb = "Updated"
        else:
            agents.append(entry)
            verb = "Registered"
        path.write_text(json.dumps(agents, indent=2), encoding="utf-8")
        return {
            "content": [{"type": "text", "text": f"{verb} agent '{agent_name}' in registry."}]
        }

    if action == "remove":
        agent_name = args.get("agent_name", "")
        remaining = [a for a in agents if a.get("name") != agent_name]
        if len(remaining) == len(agents):
            return {
                "content": [{"type": "text", "text": f"Agent '{agent_name}' not found in registry."}],
                "is_error": True,
            }
        path.write_text(json.dumps(remaining, indent=2), encoding="utf-8")
        return {
            "content": [{"type": "text", "text": f"Removed agent '{agent_name}' from registry."}]
        }

    if action == "list":
        if not agents:
            return {"content": [{"type": "text", "text": "No agents registered yet."}]}
        # Read tolerantly — older entries may lack some fields.
        lines = [
            f"- **{a.get('name', '?')}**: {a.get('description', '')} "
            f"({len(a.get('tools', []))} tools, {a.get('status', 'active')})"
            for a in agents
        ]
        return {"content": [{"type": "text", "text": "Registered agents:\n" + "\n".join(lines)}]}

    if action == "describe":
        agent_name = args.get("agent_name", "")
        match = next((a for a in agents if a.get("name") == agent_name), None)
        if not match:
            return {
                "content": [{"type": "text", "text": f"Agent '{agent_name}' not found in registry."}],
                "is_error": True,
            }
        # Surface the new SDK-config fields with tolerant defaults so older
        # entries (written before these fields existed) still describe cleanly.
        view = {
            "name": match.get("name", agent_name),
            "description": match.get("description", ""),
            "tools": match.get("tools", []),
            "created": match.get("created"),
            "updated_at": match.get("updated_at", match.get("created")),
            "path": match.get("path", f"output/{agent_name}/"),
            "status": match.get("status", "active"),
            "max_turns": match.get("max_turns"),
            "max_budget_usd": match.get("max_budget_usd"),
            "permission_mode": match.get("permission_mode"),
        }
        details = json.dumps(view, indent=2)
        return {"content": [{"type": "text", "text": f"Agent details:\n{details}"}]}

    return {
        "content": [{"type": "text", "text": f"Unknown action: {action}"}],
        "is_error": True,
    }


registry_tool = tool(
    "registry",
    "Manage the agent registry. Actions: 'add' (register or update), 'remove' (drop entry), 'list' (show all), 'describe' (show one). "
    "'add' accepts optional SDK-config fields: max_turns, max_budget_usd, permission_mode. "
    "Entries carry 'created' (first seen) and 'updated_at' (last add) ISO dates.",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "remove", "list", "describe"]},
            "agent_name": {"type": "string"},
            "description": {"type": "string"},
            "tools_list": {"type": "array", "items": {"type": "string"}},
            "max_turns": {"type": "integer"},
            "max_budget_usd": {"type": "number"},
            "permission_mode": {"type": "string"},
        },
        "required": ["action"],
    },
)(registry)
