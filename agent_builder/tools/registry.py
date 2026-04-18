"""registry tool — track created agents in agents.json."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

DEFAULT_REGISTRY = str(Path(__file__).parent.parent / "registry" / "agents.json")


async def registry(args: dict[str, Any], registry_file: str = DEFAULT_REGISTRY) -> dict[str, Any]:
    """Manage the agent registry (add, list, describe)."""
    path = Path(registry_file)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")

    agents: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    action = args["action"]

    if action == "add":
        agent_name = args.get("agent_name", "")
        entry = {
            "name": agent_name,
            "description": args.get("description", ""),
            "tools": args.get("tools_list", []),
            "created": date.today().isoformat(),
            "path": f"output/{agent_name}/",
            "status": "active",
        }
        existing_idx = next((i for i, a in enumerate(agents) if a["name"] == agent_name), None)
        if existing_idx is not None:
            entry["created"] = agents[existing_idx].get("created", entry["created"])
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
        remaining = [a for a in agents if a["name"] != agent_name]
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
        lines = [f"- **{a['name']}**: {a['description']} ({len(a['tools'])} tools, {a['status']})" for a in agents]
        return {"content": [{"type": "text", "text": "Registered agents:\n" + "\n".join(lines)}]}

    if action == "describe":
        agent_name = args.get("agent_name", "")
        match = next((a for a in agents if a["name"] == agent_name), None)
        if not match:
            return {
                "content": [{"type": "text", "text": f"Agent '{agent_name}' not found in registry."}],
                "is_error": True,
            }
        details = json.dumps(match, indent=2)
        return {"content": [{"type": "text", "text": f"Agent details:\n{details}"}]}

    return {
        "content": [{"type": "text", "text": f"Unknown action: {action}"}],
        "is_error": True,
    }


registry_tool = tool(
    "registry",
    "Manage the agent registry. Actions: 'add' (register or update), 'remove' (drop entry), 'list' (show all), 'describe' (show one).",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "remove", "list", "describe"]},
            "agent_name": {"type": "string"},
            "description": {"type": "string"},
            "tools_list": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action"],
    },
)(registry)
