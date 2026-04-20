"""attach_recipe builder tool — materializes a recipe into a generated agent.

Phase B implements tool-type recipes via **composition** (per the v0.9
composition retrofit plan):

1. Copy `recipes/tools/<slug>/tool.py` to `output/<agent>/_recipes/<slug>.py`
   (hyphens in the slug become underscores for the Python module name).
2. Update `.recipe_manifest.json` with an `AttachedRecipe` entry.
3. Call `render_agent(agent_dir)` which rewrites `agent.py` + `AGENT.md`
   deterministically from the manifest (imports, mcp_servers dict, RECIPE_PINS).

Sprint 4 (D3) adds mcp-type recipes via the same manifest + render path:

1. Validate the recipe's `mcp.json` `env_passthrough` entries against the
   recipe's declared `env_keys`.
2. Copy `mcp.json` to `output/<agent>/_recipes/<slug>.mcp.json` — render.py
   reads it back from there to emit the `external_mcp_block` entry.
3. Update the manifest with an mcp-type `AttachedRecipe` entry.
4. Call `render_agent(agent_dir)` to rebuild `agent.py` from manifest state.
5. Merge the recipe's `env_keys` into `.env.example` under a versioned banner.

Idempotent per `(agent, recipe@version)` — re-running is a no-op (manifest
unchanged, recipe file untouched).
"""

import datetime
import json
import re
import shutil
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
from agent_builder.paths import SLUG_PATTERN, validate_relative_to_base
from agent_builder.recipes.loader import default_recipes_root, load_all_recipes
from agent_builder.recipes.schema import Recipe, RecipeError, RecipeType
from agent_builder.render import render_agent


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

    if not SLUG_PATTERN.match(recipe_name):
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

    if recipe.type is RecipeType.MCP:
        return _attach_mcp_recipe(recipe, agent_dir, resolved_recipes_root)

    return _error(f"Recipe type '{recipe.type.value}' not yet supported.")


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

    # Tool recipes may also declare env_keys (e.g. telegram-poll needs
    # TELEGRAM_BOT_TOKEN). Merge them into .env.example before touching the
    # manifest so a conflict aborts cleanly.
    if recipe.env_keys:
        try:
            _merge_env_example(agent_dir / ".env.example", recipe)
        except RuntimeError as e:
            return _error(str(e))

    # If this recipe is a poll source, claim the manifest slot. Only one
    # recipe may expose a poll source per agent — a conflicting claim fails
    # here before anything is written to the manifest.
    if recipe.poll_source:
        if manifest.poll_source and manifest.poll_source != recipe.name:
            return _error(
                f"Cannot attach poll-source recipe '{recipe.name}': agent "
                f"'{agent_dir.name}' already has poll source "
                f"'{manifest.poll_source}'. Only one poll source per agent."
            )
        manifest.poll_source = recipe.name

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


def _attach_mcp_recipe(
    recipe: Recipe,
    agent_dir: Path,
    recipes_root: Path,
) -> dict[str, Any]:
    """Composition-based attach for mcp-type recipes.

    Copy the recipe's `mcp.json` into `agent_dir/_recipes/<slug>.mcp.json`
    (where `render_agent` will find it), update the manifest, regenerate
    `agent.py`, and merge the recipe's `env_keys` into `.env.example`.
    """
    manifest_path = agent_dir / MANIFEST_FILENAME
    manifest = load_manifest(manifest_path, agent_name=agent_dir.name)
    existing = next((r for r in manifest.recipes if r.name == recipe.name), None)
    if existing is not None and existing.version == recipe.version:
        return _ok(
            f"Recipe '{recipe.name}@{recipe.version}' already attached to "
            f"{agent_dir.name}."
        )

    # Load + validate the recipe's mcp.json.
    src = recipes_root / "mcps" / recipe.name / "mcp.json"
    if not src.exists():
        return _error(f"Recipe mcp.json missing at {src} — recipe library broken.")
    try:
        cfg = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return _error(f"Recipe mcp.json at {src} is not valid JSON: {e}")
    if not isinstance(cfg, dict):
        return _error(f"Recipe mcp.json at {src} must be a JSON object.")

    env_passthrough = cfg.get("env_passthrough", [])
    if env_passthrough and not isinstance(env_passthrough, list):
        return _error(
            f"Recipe '{recipe.name}' mcp.json 'env_passthrough' must be a list."
        )
    declared = {k.name for k in recipe.env_keys}
    unknown = [e for e in env_passthrough if e not in declared]
    if unknown:
        return _error(
            f"Recipe '{recipe.name}' mcp.json env_passthrough keys {unknown} "
            f"are not declared in RECIPE.md env_keys {sorted(declared)}."
        )

    # Merge .env.example BEFORE mutating the manifest / copying files so a
    # conflict aborts cleanly leaving the agent untouched.
    try:
        _merge_env_example(agent_dir / ".env.example", recipe)
    except RuntimeError as e:
        return _error(str(e))

    # Copy the mcp.json into _recipes/<slug>.mcp.json — render.py reads it.
    recipes_dir = agent_dir / "_recipes"
    recipes_dir.mkdir(exist_ok=True)
    dst = recipes_dir / f"{_slug_to_module(recipe.name)}.mcp.json"
    shutil.copyfile(src, dst)

    # Update manifest: replace any prior entry (version change) with the new one.
    if existing is not None:
        manifest.recipes = [r for r in manifest.recipes if r.name != recipe.name]
    manifest.recipes.append(AttachedRecipe(
        name=recipe.name,
        type="mcp",
        version=recipe.version,
        attached_at=_today_iso(),
        git_sha=_short_sha(),
    ))
    save_manifest(manifest_path, manifest)

    render_agent(agent_dir)

    if recipe.oauth_scopes:
        try:
            _render_setup_auth(recipe, agent_dir, recipes_root)
        except RuntimeError as e:
            return _error(str(e))

    return _ok(
        f"Attached mcp recipe '{recipe.name}@{recipe.version}' to "
        f"{agent_dir.name} via composition."
    )


def _render_setup_auth(recipe: Recipe, agent_dir: Path, recipes_root: Path) -> None:
    """Render the recipe's setup_auth.py.tmpl into the agent dir.

    Only called for mcp-type recipes that declare ``oauth_scopes``. Convention:
    the first ``env_keys`` entry is the client-secrets path, the second is the
    token storage path. Fills ``{{scopes}}`` with the Python ``repr`` of the
    scopes list so the rendered file contains a valid list literal.
    """
    tmpl_path = recipes_root / "mcps" / recipe.name / "setup_auth.py.tmpl"
    tmpl = tmpl_path.read_text(encoding="utf-8")

    if len(recipe.env_keys) < 2:
        raise RuntimeError(
            f"{recipe.name}: oauth-capable mcp recipe must declare at least 2 env_keys "
            "(client_secrets path, token path) in that order"
        )
    client_secrets_env = recipe.env_keys[0].name
    token_path_env = recipe.env_keys[1].name

    rendered = (
        tmpl
        .replace("{{scopes}}", repr(recipe.oauth_scopes))
        .replace("{{client_secrets_env}}", client_secrets_env)
        .replace("{{token_path_env}}", token_path_env)
        .replace("{{recipe_name}}", recipe.name)
    )

    leftover = re.findall(r"\{\{[^}]+\}\}", rendered)
    if leftover:
        raise RuntimeError(
            f"{recipe.name}/setup_auth.py.tmpl: unfilled placeholders after render: {leftover}"
        )

    (agent_dir / "setup_auth.py").write_text(rendered, encoding="utf-8")

    agent_md = agent_dir / "AGENT.md"
    if agent_md.exists():
        existing = agent_md.read_text(encoding="utf-8")
        banner = (
            f"\n\n## First-run setup — {recipe.name}\n\n"
            f"Run `python setup_auth.py` once before starting this agent — grants {recipe.name} access.\n"
        )
        if banner not in existing:
            agent_md.write_text(existing + banner, encoding="utf-8")


_ENV_RECIPE_BANNER = re.compile(
    r"^# --- from recipe: (?P<name>\S+) @ (?P<version>\S+) ---$",
    re.MULTILINE,
)


def _merge_env_example(env_path: Path, recipe: Recipe) -> None:
    """Append the recipe's env_keys to the agent's .env.example.

    Idempotent: if a banner for this recipe+version is already present, no-op.
    Raises RuntimeError if any of the recipe's keys are already declared by a
    non-banner line (a genuine conflict that the user must resolve).
    """
    current = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    # Idempotency: exact banner+version already present -> no-op.
    for m in _ENV_RECIPE_BANNER.finditer(current):
        if m.group("name") == recipe.name and m.group("version") == recipe.version:
            return

    # Conflict detection: any of our keys already declared by a NON-banner line?
    my_keys = {k.name for k in recipe.env_keys}
    for line in current.splitlines():
        s = line.strip()
        if "=" in s and not s.startswith("#"):
            key = s.split("=", 1)[0]
            if key in my_keys:
                raise RuntimeError(
                    f"env key '{key}' already in .env.example — conflict with "
                    f"recipe {recipe.name}"
                )

    block = [f"\n# --- from recipe: {recipe.name} @ {recipe.version} ---"]
    for k in recipe.env_keys:
        block.append(f"# {k.description}")
        block.append(f"{k.name}={k.example}")
    env_path.write_text(
        current.rstrip() + "\n" + "\n".join(block) + "\n",
        encoding="utf-8",
    )


def _slug_to_module(slug: str) -> str:
    """Convert a recipe slug to a valid Python module name.

    Slugs may start with a digit (SLUG_PATTERN allows ``^[a-z0-9]...``) but
    Python module names may not — prefix with ``_`` when the slug is
    digit-leading. Must stay in lockstep with render._slug_to_module so the
    two sides agree on the on-disk filename and the import line.
    """
    mod = slug.replace("-", "_")
    if mod and mod[0].isdigit():
        mod = "_" + mod
    return mod


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
    if not SLUG_PATTERN.match(agent_name):
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
    "generated agent. Supports tool-type (copy tool.py into _recipes/<slug>.py) "
    "and mcp-type (copy mcp.json into _recipes/<slug>.mcp.json, merge env_keys "
    "into .env.example) recipes. The manifest is updated and agent.py is "
    "regenerated from manifest state via render_agent. Idempotent per "
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
