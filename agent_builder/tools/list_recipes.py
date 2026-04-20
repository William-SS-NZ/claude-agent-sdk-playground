"""list_recipes builder tool — returns a compact index of available recipes."""

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder.recipes.loader import default_recipes_root, load_all_recipes
from agent_builder.recipes.schema import RecipeError


async def list_recipes(
    args: dict[str, Any],
    *,
    recipes_root: Path | None = None,
) -> dict[str, Any]:
    """Return a compact JSON index of available recipes, optionally filtered."""
    type_filter = args.get("type")
    tag_filter = args.get("tag")

    try:
        recipes = load_all_recipes(recipes_root or default_recipes_root())
    except RecipeError as e:
        return {"content": [{"type": "text", "text": f"Recipe load error: {e}"}], "is_error": True}

    index = [
        {
            "name": r.name,
            "type": r.type.value,
            "version": r.version,
            "description": r.description,
            "when_to_use": r.when_to_use,
            "tags": r.tags,
        }
        for r in recipes
        if (type_filter is None or r.type.value == type_filter)
        and (tag_filter is None or tag_filter in r.tags)
    ]

    return {"content": [{"type": "text", "text": json.dumps(index, indent=2)}]}


list_recipes_tool = tool(
    "list_recipes",
    "List available recipes (MCPs, tools, skills) that can be attached to a generated agent. "
    "Returns a compact JSON index with name, type, version, description, when_to_use, tags. "
    "Call this during Phase 2 (Tool Design) to check for reusable components before "
    "designing bespoke tools. Optional filters: type (mcp|tool|skill), tag (single tag string).",
    {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["mcp", "tool", "skill"]},
            "tag": {"type": "string"},
        },
    },
)(list_recipes)
