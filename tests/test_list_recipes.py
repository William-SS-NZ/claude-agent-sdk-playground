"""Tests for the list_recipes builder tool."""

import json
from pathlib import Path

import pytest

from agent_builder.tools.list_recipes import list_recipes

FIXTURES = Path(__file__).parent / "fixtures" / "recipes_valid"


@pytest.mark.asyncio
async def test_list_recipes_returns_compact_index():
    result = await list_recipes({}, recipes_root=FIXTURES)
    assert result.get("is_error") is not True
    payload = json.loads(result["content"][0]["text"])
    assert isinstance(payload, list)
    names = [r["name"] for r in payload]
    assert "hello-world" in names
    r = next(r for r in payload if r["name"] == "hello-world")
    assert r["type"] == "tool"
    assert "description" in r
    # Prose body must be stripped from the compact index.
    assert "body" not in r


@pytest.mark.asyncio
async def test_list_recipes_filters_by_type():
    result = await list_recipes({"type": "mcp"}, recipes_root=FIXTURES)
    payload = json.loads(result["content"][0]["text"])
    # hello-world is a tool, not an mcp; filter should exclude it.
    assert all(r["type"] == "mcp" for r in payload)


@pytest.mark.asyncio
async def test_list_recipes_filters_by_tag():
    result = await list_recipes({"tag": "test"}, recipes_root=FIXTURES)
    payload = json.loads(result["content"][0]["text"])
    assert any(r["name"] == "hello-world" for r in payload)

    result = await list_recipes({"tag": "nonexistent-tag-xyz"}, recipes_root=FIXTURES)
    payload = json.loads(result["content"][0]["text"])
    assert payload == []


@pytest.mark.asyncio
async def test_list_recipes_surfaces_load_errors(tmp_path):
    bad_dir = tmp_path / "tools" / "broken"
    bad_dir.mkdir(parents=True)
    (bad_dir / "RECIPE.md").write_text("not frontmatter", encoding="utf-8")
    result = await list_recipes({}, recipes_root=tmp_path)
    assert result["is_error"] is True
    assert "frontmatter" in result["content"][0]["text"]
