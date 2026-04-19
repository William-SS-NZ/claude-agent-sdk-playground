"""attach_recipe builder tool — materializes a recipe into a generated agent.

Phase B implements tool-type recipes via **composition** (per the v0.9
composition retrofit plan):

1. Copy `recipes/tools/<slug>/tool.py` to `output/<agent>/_recipes/<slug>.py`
   (hyphens in the slug become underscores for the Python module name).
2. Update `.recipe_manifest.json` with an `AttachedRecipe` entry.
3. Call `render_agent(agent_dir)` which rewrites `agent.py` + `AGENT.md`
   deterministically from the manifest (imports, mcp_servers dict, RECIPE_PINS).

Idempotent per `(agent, recipe@version)` — re-running is a no-op (manifest
unchanged, recipe file untouched).
"""

import datetime
import re
import subprocess
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder.manifest import (
    MANIFEST_FILENAME,
    AttachedRecipe,
    load_manifest,
    save_manifest,
)
from agent_builder.paths import validate_relative_to_base
from agent_builder.recipes.loader import default_recipes_root, load_all_recipes
from agent_builder.recipes.schema import Recipe, RecipeError, RecipeType
from agent_builder.render import render_agent

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


async def attach_recipe(
    args: dict[str, Any],
    *,
    output_base: str = "output",
    recipes_root: Path | None = None,
) -> dict[str, Any]:
    """Attach a recipe to an existing generated agent.

    Returns MCP-shape ``{"content": [...], "is_error"?: bool}``.
    """
    agent_name = args.get("agent_name", "")
    recipe_name = args.get("recipe_name", "")

    err = _validate_agent_name(agent_name, output_base)
    if err:
        return _error(err)

    if not _NAME_PATTERN.match(recipe_name):
        return _error(f"Invalid recipe name '{recipe_name}'.")

    agent_dir = Path(output_base) / agent_name
    if not agent_dir.exists():
        return _error(f"Agent '{agent_name}' not found at {agent_dir}")

    resolved_recipes_root = recipes_root or default_recipes_root()
    try:
        recipes = load_all_recipes(resolved_recipes_root)
    except RecipeError as e:
        return _error(f"Recipe load error: {e}")

    recipe = next((r for r in recipes if r.name == recipe_name), None)
    if recipe is None:
        return _error(f"Recipe '{recipe_name}' not found in recipes library.")

    if recipe.type is RecipeType.TOOL:
        return _attach_tool_recipe(recipe, agent_dir, resolved_recipes_root)

    return _error(
        f"Recipe type '{recipe.type.value}' not yet supported "
        "(Phase B ships tool-type only)."
    )


def _attach_tool_recipe(
    recipe: Recipe,
    agent_dir: Path,
    recipes_root: Path,
) -> dict[str, Any]:
    """Composition-based attach for tool-type recipes.

    Copy recipe `tool.py` into `agent_dir/_recipes/<slug>.py`, update the
    manifest, then let `render_agent` rebuild `agent.py` from manifest state.
    """
    # Idempotency: if already attached at the same version, return early
    # *without* touching files so the recipe mtime stays stable.
    manifest_path = agent_dir / MANIFEST_FILENAME
    manifest = load_manifest(manifest_path, agent_name=agent_dir.name)
    existing = next((r for r in manifest.recipes if r.name == recipe.name), None)
    if existing is not None and existing.version == recipe.version:
        return _ok(
            f"Recipe '{recipe.name}@{recipe.version}' already attached to "
            f"{agent_dir.name}."
        )

    # Copy recipe source into agent's _recipes/ dir (hyphens → underscores).
    recipes_dir = agent_dir / "_recipes"
    recipes_dir.mkdir(exist_ok=True)
    src = recipes_root / "tools" / recipe.name / "tool.py"
    if not src.exists():
        return _error(f"Recipe tool.py missing at {src} — recipe library broken.")
    dst = recipes_dir / f"{_slug_to_module(recipe.name)}.py"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    # Update manifest: drop any prior entry for this recipe (version change),
    # then append the new one.
    if existing is not None:
        manifest.recipes = [r for r in manifest.recipes if r.name != recipe.name]
    manifest.recipes.append(AttachedRecipe(
        name=recipe.name,
        type="tool",
        version=recipe.version,
        attached_at=_today_iso(),
        git_sha=_short_sha(),
    ))
    save_manifest(manifest_path, manifest)

    # Regenerate agent.py + AGENT.md from manifest.
    render_agent(agent_dir)

    return _ok(
        f"Attached tool recipe '{recipe.name}@{recipe.version}' to "
        f"{agent_dir.name} via composition."
    )


def _slug_to_module(slug: str) -> str:
    """Convert a recipe slug to a valid Python module name."""
    return slug.replace("-", "_")


def _today_iso() -> str:
    """ISO date string for manifest `attached_at` field."""
    return datetime.date.today().isoformat()


def _short_sha() -> str:
    """Current short (7-char) git SHA, or '' when git is unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def _validate_agent_name(agent_name: str, output_base: str) -> str | None:
    """Slug + path-containment check. Same shape as scaffold/remove_agent."""
    if not _NAME_PATTERN.match(agent_name):
        return (
            f"Invalid agent name '{agent_name}'. "
            "Must match ^[a-z0-9][a-z0-9-]*$."
        )
    if ".." in agent_name or "/" in agent_name or "\\" in agent_name:
        return (
            f"Invalid agent name '{agent_name}'. "
            "Must not contain '..', '/', or '\\\\'."
        )
    _, err = validate_relative_to_base(
        str(Path(output_base) / agent_name),
        [Path(output_base)],
    )
    if err is not None:
        return f"Invalid agent name '{agent_name}'. Path traversal detected."
    return None


def _error(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}], "is_error": True}


def _ok(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}


attach_recipe_tool = tool(
    "attach_recipe",
    "Materialize a recipe from the bundled recipes library into an existing "
    "generated agent. Phase B supports tool-type recipes only: the recipe's "
    "tool.py is copied into the agent's _recipes/<slug>.py, the manifest is "
    "updated, and agent.py is regenerated from the manifest. Idempotent per "
    "(agent, recipe@version).",
    {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string"},
            "recipe_name": {"type": "string"},
        },
        "required": ["agent_name", "recipe_name"],
    },
)(attach_recipe)
