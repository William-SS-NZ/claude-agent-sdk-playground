"""Recipe filesystem loader.

Walks agent_builder/recipes/{mcps,tools,skills}/<slug>/ and returns
validated Recipe objects. Siblings required by recipe type are
checked (mcp.json for MCP recipes, tool.py for tool recipes, etc.)
so malformed recipes fail loudly at load time rather than silently
during attach_recipe.
"""

from pathlib import Path

from agent_builder.recipes.schema import Recipe, RecipeError, RecipeType, parse_recipe_md

_TYPE_DIRS: dict[RecipeType, str] = {
    RecipeType.MCP: "mcps",
    RecipeType.TOOL: "tools",
    RecipeType.SKILL: "skills",
}


def default_recipes_root() -> Path:
    """Return the default bundled-recipes root inside agent_builder/."""
    return Path(__file__).parent


def load_all_recipes(recipes_root: Path | None = None) -> list[Recipe]:
    """Scan recipes_root/{mcps,tools,skills}/* and return every valid Recipe."""
    root = Path(recipes_root) if recipes_root else default_recipes_root()
    recipes: list[Recipe] = []
    for type_, dirname in _TYPE_DIRS.items():
        type_dir = root / dirname
        if not type_dir.exists():
            continue
        for entry in sorted(type_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            recipes.append(load_recipe(entry, expected_type=type_))
    return recipes


def load_recipe(recipe_dir: Path, expected_type: RecipeType | None = None) -> Recipe:
    """Load and validate a single recipe directory."""
    recipe_dir = Path(recipe_dir)
    md_path = recipe_dir / "RECIPE.md"
    if not md_path.exists():
        raise RecipeError(f"{recipe_dir}: missing RECIPE.md")
    content = md_path.read_text(encoding="utf-8")
    recipe = parse_recipe_md(content, source_path=str(md_path))

    if recipe.name != recipe_dir.name:
        raise RecipeError(
            f"{md_path}: frontmatter name '{recipe.name}' does not match dir name '{recipe_dir.name}'"
        )

    if expected_type is not None and recipe.type is not expected_type:
        raise RecipeError(
            f"{md_path}: recipe under {_TYPE_DIRS[expected_type]}/ must declare type={expected_type.value}, "
            f"got type={recipe.type.value}"
        )

    _validate_sibling_files(recipe, recipe_dir)
    return recipe


def _validate_sibling_files(recipe: Recipe, recipe_dir: Path) -> None:
    if recipe.type is RecipeType.MCP:
        if not (recipe_dir / "mcp.json").exists():
            raise RecipeError(f"{recipe_dir}: mcp recipe missing mcp.json")
        if recipe.oauth_scopes and not (recipe_dir / "setup_auth.py.tmpl").exists():
            raise RecipeError(
                f"{recipe_dir}: mcp recipe declares oauth_scopes but has no setup_auth.py.tmpl"
            )
    elif recipe.type is RecipeType.TOOL:
        if not (recipe_dir / "tool.py").exists():
            raise RecipeError(f"{recipe_dir}: tool recipe missing tool.py")
    elif recipe.type is RecipeType.SKILL:
        if not (recipe_dir / "skill.md").exists():
            raise RecipeError(f"{recipe_dir}: skill recipe missing skill.md")
