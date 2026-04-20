"""Tests for filesystem loading of recipes."""

from pathlib import Path

import pytest

from agent_builder.recipes.loader import load_all_recipes, load_recipe
from agent_builder.recipes.schema import RecipeError, RecipeType

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_all_recipes_returns_valid():
    recipes = load_all_recipes(FIXTURES / "recipes_valid")
    assert len(recipes) >= 1
    names = {r.name for r in recipes}
    assert "hello-world" in names
    r = next(r for r in recipes if r.name == "hello-world")
    assert r.type is RecipeType.TOOL


def test_load_all_recipes_rejects_mismatched_files():
    with pytest.raises(RecipeError, match="mcp.json"):
        load_all_recipes(FIXTURES / "recipes_invalid")


def test_load_all_recipes_empty_dir_ok(tmp_path):
    (tmp_path / "mcps").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "skills").mkdir()
    assert load_all_recipes(tmp_path) == []


def test_load_recipe_single(tmp_path):
    recipe_dir = tmp_path / "tools" / "x"
    recipe_dir.mkdir(parents=True)
    (recipe_dir / "RECIPE.md").write_text(
        "---\nname: x\ntype: tool\nversion: 0.1.0\ndescription: x\nwhen_to_use: x\n---\n",
        encoding="utf-8",
    )
    (recipe_dir / "tool.py").write_text("# empty", encoding="utf-8")
    r = load_recipe(recipe_dir)
    assert r.name == "x"


def test_load_recipe_name_must_match_dir(tmp_path):
    recipe_dir = tmp_path / "tools" / "foo"
    recipe_dir.mkdir(parents=True)
    (recipe_dir / "RECIPE.md").write_text(
        "---\nname: bar\ntype: tool\nversion: 0.1.0\ndescription: x\nwhen_to_use: x\n---\n",
        encoding="utf-8",
    )
    (recipe_dir / "tool.py").write_text("# empty", encoding="utf-8")
    with pytest.raises(RecipeError, match="dir name"):
        load_recipe(recipe_dir)
