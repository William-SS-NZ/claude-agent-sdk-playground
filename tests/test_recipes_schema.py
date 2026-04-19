"""Tests for recipe schema parsing and validation."""

import pytest

from agent_builder.recipes.schema import (
    Recipe,
    RecipeType,
    RecipeError,
    parse_recipe_md,
)


def test_parse_valid_tool_recipe():
    content = """---
name: telegram-poll
type: tool
version: 0.1.0
description: Long-polls Telegram bot API for incoming messages.
when_to_use: Agent runs in poll mode and reacts to Telegram DMs.
allowed_tools_patterns:
  - mcp__agent_tools__telegram_poll_source
tags: [telegram, messaging, poll]
---

# Telegram Poll

Prose body here.
"""
    recipe = parse_recipe_md(content, source_path="/fake/telegram-poll/RECIPE.md")
    assert recipe.name == "telegram-poll"
    assert recipe.type is RecipeType.TOOL
    assert recipe.version == "0.1.0"
    assert recipe.description.startswith("Long-polls")
    assert recipe.allowed_tools_patterns == ["mcp__agent_tools__telegram_poll_source"]
    assert recipe.tags == ["telegram", "messaging", "poll"]
    assert recipe.env_keys == []
    assert recipe.oauth_scopes == []


def test_parse_valid_mcp_recipe_with_oauth():
    content = """---
name: google-calendar
type: mcp
version: 0.1.0
description: Read/write Google Calendar events.
when_to_use: Agent needs to create or update calendar events.
env_keys:
  - name: GOOGLE_OAUTH_CLIENT_SECRETS
    description: Path to OAuth client JSON.
    example: ./credentials.json
oauth_scopes:
  - https://www.googleapis.com/auth/calendar
allowed_tools_patterns:
  - mcp__gcal__*
tags: [calendar, google, oauth]
---

Body.
"""
    recipe = parse_recipe_md(content, source_path="/fake/google-calendar/RECIPE.md")
    assert recipe.type is RecipeType.MCP
    assert recipe.oauth_scopes == ["https://www.googleapis.com/auth/calendar"]
    assert len(recipe.env_keys) == 1
    assert recipe.env_keys[0].name == "GOOGLE_OAUTH_CLIENT_SECRETS"


def test_parse_rejects_missing_frontmatter():
    content = "# Just markdown, no frontmatter\n"
    with pytest.raises(RecipeError, match="frontmatter"):
        parse_recipe_md(content, source_path="/fake/RECIPE.md")


def test_parse_rejects_invalid_name():
    content = """---
name: Bad_Name
type: tool
version: 0.1.0
description: x
when_to_use: x
---
"""
    with pytest.raises(RecipeError, match="name"):
        parse_recipe_md(content, source_path="/fake/RECIPE.md")


def test_parse_rejects_unknown_type():
    content = """---
name: ok
type: widget
version: 0.1.0
description: x
when_to_use: x
---
"""
    with pytest.raises(RecipeError, match="type"):
        parse_recipe_md(content, source_path="/fake/RECIPE.md")


def test_parse_rejects_bad_semver():
    content = """---
name: ok
type: tool
version: nine
description: x
when_to_use: x
---
"""
    with pytest.raises(RecipeError, match="version"):
        parse_recipe_md(content, source_path="/fake/RECIPE.md")
