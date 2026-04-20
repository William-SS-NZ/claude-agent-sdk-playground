"""Tests for attach_recipe's .env.example merger conflict detection."""

import pytest

from agent_builder.recipes.schema import EnvKey, Recipe, RecipeType
from agent_builder.tools.attach_recipe import _merge_env_example


def _make(name, keys):
    return Recipe(
        name=name,
        type=RecipeType.MCP,
        version="0.1.0",
        description="x",
        when_to_use="x",
        env_keys=[EnvKey(name=k, description="x", example="y") for k in keys],
    )


def test_merge_env_example_conflict(tmp_path):
    env = tmp_path / ".env.example"
    env.write_text("SHARED_KEY=foo\n", encoding="utf-8")
    r = _make("other", ["SHARED_KEY"])
    with pytest.raises(RuntimeError, match="SHARED_KEY"):
        _merge_env_example(env, r)


def test_merge_env_example_no_conflict(tmp_path):
    env = tmp_path / ".env.example"
    env.write_text("UNRELATED=foo\n", encoding="utf-8")
    r = _make("clean", ["FRESH_KEY"])
    _merge_env_example(env, r)
    content = env.read_text()
    assert "FRESH_KEY" in content
    assert "# --- from recipe: clean @ 0.1.0 ---" in content
