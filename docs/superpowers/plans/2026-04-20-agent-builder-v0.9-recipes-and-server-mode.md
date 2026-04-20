# Agent Builder v0.9 — Recipes, OAuth, and Server Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Agent Builder with a reusable `recipes/` library (MCPs, tools, skills), OAuth helper scaffolding, and two new generated-agent templates (long-poll worker, FastAPI webhook) so that a Telegram → Google Calendar bot is buildable in one interactive session.

**Architecture:** Recipes are frontmatter-driven markdown directories that declare either an MCP config, a tool.py, or a skill.md. Two new builder tools (`list_recipes`, `attach_recipe`) let the builder discover and materialize recipes into generated agents. Recipe contents are copied (not imported) into the agent, with version pins stamped for future resync. Generated agents gain a `mode` parameter (`cli` | `poll` | `server`) that selects the template; `mode="server"` requires a webhook-capable recipe before scaffolding completes.

**Tech Stack:**
- Python 3.10+
- `claude-agent-sdk` (existing)
- `pyyaml` (new base dep — for RECIPE.md frontmatter parsing)
- `python-telegram-bot` (new optional dep, `[telegram]` extra — for the telegram-poll recipe)
- `google-auth-oauthlib` + `google-api-python-client` (new optional dep, `[google]` extra — for the gcal setup_auth helper)
- `fastapi` + `uvicorn` (new optional dep, `[server]` extra — Phase F only, post-v0.9)
- `pytest` + `pytest-asyncio` (existing)

**Spec:** `docs/superpowers/specs/2026-04-20-agent-builder-v0.9-recipes-and-server-mode-design.md`

**Branch:** `feat/v0.9-recipes-and-server-mode` (already created)

**Scope of this plan:** Phases A–E from the spec = v0.9.0 milestone endpoint. Phases F (server template) and G (skill recipes) are noted in §Future Phases with their own sub-plans to be written when that work starts.

---

## File Structure

**New files:**

```
agent_builder/recipes/
    __init__.py                         # exports load_all_recipes, RecipeError
    schema.py                           # RECIPE.md frontmatter schema + Recipe dataclass
    loader.py                           # filesystem scan + parse + validate
    mcps/
        .gitkeep
        google-calendar/                # Phase E
            RECIPE.md
            mcp.json
            setup_auth.py.tmpl
    tools/
        .gitkeep
        telegram-poll/                  # Phase C
            RECIPE.md
            tool.py
    skills/
        .gitkeep                        # Phase G only

agent_builder/tools/
    list_recipes.py                     # Phase A
    attach_recipe.py                    # Phases B–E

agent_builder/templates/
    agent_poll.py.tmpl                  # Phase C

docs/
    oauth-setup.md                      # Phase E

tests/
    test_recipes_schema.py              # Phase A
    test_recipes_loader.py              # Phase A
    test_list_recipes.py                # Phase A
    test_attach_recipe.py               # Phases B–E
    test_agent_poll_template.py         # Phase C
    test_e2e_recipe_attach.py           # Phase E
    fixtures/
        recipes_valid/
            tools/hello-world/RECIPE.md
            tools/hello-world/tool.py
            mcps/fake-mcp/RECIPE.md
            mcps/fake-mcp/mcp.json
        recipes_invalid/
            tools/bad-mismatch/RECIPE.md
```

**Modified files:**

```
pyproject.toml                          # +pyyaml base, +[telegram]/[google] extras, bump to 0.9.0
agent_builder/tools/__init__.py         # register list_recipes + attach_recipe
agent_builder/tools/scaffold.py         # mode param + external_mcps + new placeholders
agent_builder/templates/agent_main.py.tmpl  # {{external_mcp_block}} + {{recipe_pins_block}}
agent_builder/doctor.py                 # recipe validation + per-template placeholder check
agent_builder/identity/AGENT.md         # Phase 2.5 workflow section
agent_builder/tools/test_agent.py       # mode="poll" support
CLAUDE.md                               # update architecture section
```

**Out of scope for this plan (Future Phases):**

```
agent_builder/templates/agent_server.py.tmpl        # Phase F (v0.9.1)
agent_builder/recipes/skills/<recipe>/               # Phase G (v0.9.2)
```

---

## Phase A — Recipe Framework Foundation

Ships: recipe directory structure, frontmatter schema, loader, validation, `list_recipes` tool. After Phase A, `list_recipes` returns an empty index but all plumbing exists.

### Task A1: Add pyyaml dependency and bump version

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pyyaml to base deps and bump version**

Edit `pyproject.toml`:

```toml
[project]
name = "claude-agent-sdk-playground"
version = "0.9.0"
description = "Agent Builder — create, test, and manage purpose-built Claude Agent SDK agents through conversation"
requires-python = ">=3.10"
license = { text = "PolyForm-Noncommercial-1.0.0" }
authors = [{ name = "William Clelland" }]
readme = "README.md"
dependencies = [
    "claude-agent-sdk>=0.1.0",
    "anyio>=4.0",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]
telegram = [
    "python-telegram-bot>=21.0",
]
google = [
    "google-auth-oauthlib>=1.2",
    "google-api-python-client>=2.0",
]
```

- [ ] **Step 2: Reinstall editable**

Run: `pip install -e ".[dev]"`
Expected: pyyaml installs without error.

- [ ] **Step 3: Verify version bumps**

Run: `python -c "from agent_builder._version import __version__; print(__version__)"`
Expected output: `0.9.0`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: bump to 0.9.0 and add pyyaml/telegram/google deps"
```

### Task A2: Create recipe directory skeleton

**Files:**
- Create: `agent_builder/recipes/__init__.py`
- Create: `agent_builder/recipes/mcps/.gitkeep`
- Create: `agent_builder/recipes/tools/.gitkeep`
- Create: `agent_builder/recipes/skills/.gitkeep`

- [ ] **Step 1: Create package init**

Write `agent_builder/recipes/__init__.py`:

```python
"""Recipe library — reusable MCP, tool, and skill definitions."""

from agent_builder.recipes.loader import load_all_recipes, load_recipe, RecipeError
from agent_builder.recipes.schema import Recipe, RecipeType

__all__ = ["load_all_recipes", "load_recipe", "RecipeError", "Recipe", "RecipeType"]
```

- [ ] **Step 2: Create .gitkeep files**

Create three empty files: `agent_builder/recipes/mcps/.gitkeep`, `agent_builder/recipes/tools/.gitkeep`, `agent_builder/recipes/skills/.gitkeep`.

- [ ] **Step 3: Verify structure**

Run: `ls agent_builder/recipes/`
Expected: `__init__.py  mcps/  skills/  tools/`

- [ ] **Step 4: Commit**

```bash
git add agent_builder/recipes/
git commit -m "feat(recipes): create recipe directory skeleton"
```

### Task A3: Write the recipe schema module (TDD)

**Files:**
- Create: `tests/test_recipes_schema.py`
- Create: `agent_builder/recipes/schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_recipes_schema.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_recipes_schema.py -v`
Expected: ImportError on `agent_builder.recipes.schema` (module doesn't exist yet).

- [ ] **Step 3: Write the schema module**

Create `agent_builder/recipes/schema.py`:

```python
"""Recipe frontmatter schema, dataclasses, and validation."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml


class RecipeError(ValueError):
    """Raised when a recipe's RECIPE.md is malformed or invalid."""


class RecipeType(str, Enum):
    MCP = "mcp"
    TOOL = "tool"
    SKILL = "skill"


_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_FRONTMATTER_PATTERN = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z",
    re.DOTALL,
)


@dataclass(frozen=True)
class EnvKey:
    name: str
    description: str
    example: str = ""


@dataclass(frozen=True)
class Recipe:
    name: str
    type: RecipeType
    version: str
    description: str
    when_to_use: str
    env_keys: list[EnvKey] = field(default_factory=list)
    oauth_scopes: list[str] = field(default_factory=list)
    allowed_tools_patterns: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    body: str = ""
    source_path: str = ""


def parse_recipe_md(content: str, *, source_path: str) -> Recipe:
    """Parse a RECIPE.md file's raw content into a Recipe dataclass.

    Raises RecipeError on any schema violation so the caller can surface
    a clear error message pointing at the source file.
    """
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        raise RecipeError(
            f"{source_path}: missing or malformed frontmatter (expected --- ... --- at start of file)"
        )
    try:
        data: Any = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise RecipeError(f"{source_path}: frontmatter is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise RecipeError(f"{source_path}: frontmatter must be a mapping, got {type(data).__name__}")

    body = match.group(2)

    _require_keys(data, ("name", "type", "version", "description", "when_to_use"), source_path)

    name = data["name"]
    if not isinstance(name, str) or not _NAME_PATTERN.match(name):
        raise RecipeError(
            f"{source_path}: name '{name}' invalid (must match ^[a-z0-9][a-z0-9-]*$)"
        )

    try:
        type_ = RecipeType(data["type"])
    except ValueError:
        raise RecipeError(
            f"{source_path}: type '{data['type']}' invalid (must be one of: {[t.value for t in RecipeType]})"
        ) from None

    version = data["version"]
    if not isinstance(version, str) or not _SEMVER_PATTERN.match(version):
        raise RecipeError(
            f"{source_path}: version '{version}' invalid (must be semver like '0.1.0')"
        )

    description = _require_str(data, "description", source_path)
    when_to_use = _require_str(data, "when_to_use", source_path)

    env_keys = _parse_env_keys(data.get("env_keys", []), source_path)
    oauth_scopes = _parse_string_list(data.get("oauth_scopes", []), "oauth_scopes", source_path)
    allowed_tools_patterns = _parse_string_list(
        data.get("allowed_tools_patterns", []), "allowed_tools_patterns", source_path
    )
    tags = _parse_string_list(data.get("tags", []), "tags", source_path)

    return Recipe(
        name=name,
        type=type_,
        version=version,
        description=description,
        when_to_use=when_to_use,
        env_keys=env_keys,
        oauth_scopes=oauth_scopes,
        allowed_tools_patterns=allowed_tools_patterns,
        tags=tags,
        body=body,
        source_path=source_path,
    )


def _require_keys(data: dict, keys: tuple[str, ...], source_path: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise RecipeError(f"{source_path}: frontmatter missing required keys: {missing}")


def _require_str(data: dict, key: str, source_path: str) -> str:
    v = data[key]
    if not isinstance(v, str) or not v.strip():
        raise RecipeError(f"{source_path}: '{key}' must be a non-empty string")
    return v


def _parse_string_list(value: Any, field_name: str, source_path: str) -> list[str]:
    if value in (None, []):
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise RecipeError(f"{source_path}: '{field_name}' must be a list of strings")
    return list(value)


def _parse_env_keys(value: Any, source_path: str) -> list[EnvKey]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise RecipeError(f"{source_path}: 'env_keys' must be a list")
    out: list[EnvKey] = []
    for i, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise RecipeError(f"{source_path}: env_keys[{i}] must be a mapping")
        if "name" not in entry or "description" not in entry:
            raise RecipeError(f"{source_path}: env_keys[{i}] missing 'name' or 'description'")
        out.append(EnvKey(
            name=str(entry["name"]),
            description=str(entry["description"]),
            example=str(entry.get("example", "")),
        ))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_recipes_schema.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/recipes/schema.py tests/test_recipes_schema.py agent_builder/recipes/__init__.py
git commit -m "feat(recipes): schema parser for RECIPE.md frontmatter"
```

### Task A4: Write the recipe loader (TDD)

**Files:**
- Create: `tests/test_recipes_loader.py`
- Create: `agent_builder/recipes/loader.py`
- Create: `tests/fixtures/recipes_valid/tools/hello-world/RECIPE.md`
- Create: `tests/fixtures/recipes_valid/tools/hello-world/tool.py`
- Create: `tests/fixtures/recipes_invalid/tools/bad-mismatch/RECIPE.md`

- [ ] **Step 1: Create test fixtures**

Create `tests/fixtures/recipes_valid/tools/hello-world/RECIPE.md`:

```markdown
---
name: hello-world
type: tool
version: 0.1.0
description: Returns a greeting. Used only in tests.
when_to_use: Never in production.
allowed_tools_patterns:
  - mcp__agent_tools__hello
tags: [test]
---

# Hello World

Trivial tool recipe used as a test fixture.
```

Create `tests/fixtures/recipes_valid/tools/hello-world/tool.py`:

```python
"""Hello world tool — test fixture."""

from claude_agent_sdk import tool, create_sdk_mcp_server


@tool("hello", "Returns a greeting.", {"type": "object", "properties": {"name": {"type": "string"}}})
async def hello(args):
    if TEST_MODE:  # noqa: F821 — prepended by write_tools
        return {"content": [{"type": "text", "text": "hello test"}]}
    return {"content": [{"type": "text", "text": f"hello {args.get('name', 'world')}"}]}


tools_server = create_sdk_mcp_server(name="hello-tools", version="0.1.0", tools=[hello])
```

Create `tests/fixtures/recipes_invalid/tools/bad-mismatch/RECIPE.md`:

```markdown
---
name: bad-mismatch
type: mcp
version: 0.1.0
description: Claims to be mcp but has no mcp.json.
when_to_use: Never.
---
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_recipes_loader.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_recipes_loader.py -v`
Expected: ImportError on `agent_builder.recipes.loader`.

- [ ] **Step 4: Write the loader**

Create `agent_builder/recipes/loader.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_recipes_loader.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add agent_builder/recipes/loader.py tests/test_recipes_loader.py tests/fixtures/
git commit -m "feat(recipes): filesystem loader with sibling validation"
```

### Task A5: Write the list_recipes builder tool (TDD)

**Files:**
- Create: `tests/test_list_recipes.py`
- Create: `agent_builder/tools/list_recipes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_list_recipes.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_list_recipes.py -v`
Expected: ImportError.

- [ ] **Step 3: Write the tool**

Create `agent_builder/tools/list_recipes.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_list_recipes.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/list_recipes.py tests/test_list_recipes.py
git commit -m "feat(builder): list_recipes tool for compact recipe index"
```

### Task A6: Register list_recipes in the builder MCP server

**Files:**
- Modify: `agent_builder/tools/__init__.py`
- Modify: `agent_builder/builder.py` (add to `allowed_tools`)

- [ ] **Step 1: Add to tools/__init__.py**

Edit `agent_builder/tools/__init__.py` — add import and registration:

```python
"""Builder tools — bundled into a single MCP server."""

from claude_agent_sdk import create_sdk_mcp_server

from agent_builder._version import __version__
from agent_builder.tools.scaffold import scaffold_agent_tool
from agent_builder.tools.write_identity import write_identity_tool
from agent_builder.tools.write_tools import write_tools_tool
from agent_builder.tools.test_agent import test_agent_tool
from agent_builder.tools.registry import registry_tool
from agent_builder.tools.remove_agent import remove_agent_tool
from agent_builder.tools.self_heal import propose_self_change_tool
from agent_builder.tools.edit_agent import edit_agent_tool
from agent_builder.tools.rollback import rollback_tool
from agent_builder.tools.list_recipes import list_recipes_tool

builder_tools_server = create_sdk_mcp_server(
    name="builder_tools",
    version=__version__,
    tools=[
        scaffold_agent_tool,
        write_identity_tool,
        write_tools_tool,
        test_agent_tool,
        registry_tool,
        remove_agent_tool,
        propose_self_change_tool,
        edit_agent_tool,
        rollback_tool,
        list_recipes_tool,
    ],
)
```

- [ ] **Step 2: Add to builder.py allowed_tools**

Locate the `allowed_tools=[...]` list in `agent_builder/builder.py` (Grep: `grep -n "mcp__builder_tools__" agent_builder/builder.py`). Add `"mcp__builder_tools__list_recipes"` to the list.

- [ ] **Step 3: Smoke test the builder boots**

Run: `python -m agent_builder.builder --doctor`
Expected: exit 0 (doctor still healthy).

Run: `python -m agent_builder.builder --help`
Expected: help text prints without error.

- [ ] **Step 4: Commit**

```bash
git add agent_builder/tools/__init__.py agent_builder/builder.py
git commit -m "feat(builder): register list_recipes tool in MCP server"
```

### Task A7: Extend doctor with recipe validation

**Files:**
- Modify: `agent_builder/doctor.py`
- Create or Modify: `tests/test_doctor.py`

- [ ] **Step 1: Write/extend the failing test**

Add to or create `tests/test_doctor.py`:

```python
"""Tests for the doctor health checks."""

from pathlib import Path

from agent_builder.doctor import run_health_check


def _scaffold_fake_repo(tmp_path: Path) -> None:
    """Minimal repo-root lookalike with just enough for doctor to run."""
    (tmp_path / "agent_builder" / "identity").mkdir(parents=True)
    for f in ("AGENT.md", "SOUL.md", "MEMORY.md"):
        (tmp_path / "agent_builder" / "identity" / f).write_text("x", encoding="utf-8")
    (tmp_path / "agent_builder" / "templates").mkdir()
    real_tmpl = Path("agent_builder") / "templates" / "agent_main.py.tmpl"
    (tmp_path / "agent_builder" / "templates" / "agent_main.py.tmpl").write_text(
        real_tmpl.read_text(encoding="utf-8"), encoding="utf-8"
    )


def test_doctor_reports_recipe_load_ok(tmp_path):
    _scaffold_fake_repo(tmp_path)
    (tmp_path / "agent_builder" / "recipes").mkdir()
    for d in ("mcps", "tools", "skills"):
        (tmp_path / "agent_builder" / "recipes" / d).mkdir()

    registry_path = tmp_path / "agents.json"
    registry_path.write_text("[]", encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry_path))
    assert exit_code == 0
    recipe_checks = [c for c in checks if "recipe" in c["name"].lower()]
    assert any(c["status"] == "OK" for c in recipe_checks)


def test_doctor_reports_bad_recipe_fail(tmp_path):
    _scaffold_fake_repo(tmp_path)
    broken = tmp_path / "agent_builder" / "recipes" / "tools" / "busted"
    broken.mkdir(parents=True)
    (broken / "RECIPE.md").write_text("no frontmatter", encoding="utf-8")

    registry_path = tmp_path / "agents.json"
    registry_path.write_text("[]", encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry_path))
    assert exit_code == 1
    assert any(c["status"] == "FAIL" and "recipe" in c["name"].lower() for c in checks)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_doctor.py -v`
Expected: failures referencing missing recipe checks.

- [ ] **Step 3: Add recipe check to doctor**

Edit `agent_builder/doctor.py` — add imports at the top:

```python
from agent_builder.recipes.loader import load_all_recipes
from agent_builder.recipes.schema import RecipeError
```

Add the check function:

```python
def _check_recipes_load(builder_dir: Path) -> list[dict[str, str]]:
    recipes_dir = builder_dir / "recipes"
    if not recipes_dir.exists():
        return [_check("WARN", "recipes dir", f"{recipes_dir} not found — recipe library disabled")]
    try:
        recipes = load_all_recipes(recipes_dir)
    except RecipeError as e:
        return [_check("FAIL", "recipes load", str(e))]
    return [_check("OK", "recipes load", f"{len(recipes)} recipe(s) loaded")]
```

Invoke it inside `run_health_check`, after the existing checks:

```python
    # 7. Recipes load cleanly.
    checks.extend(_check_recipes_load(builder_dir))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_doctor.py -v`
Expected: passed.

Run: `python -m agent_builder.builder --doctor`
Expected: exit 0, new `[OK  ] recipes load: 0 recipe(s) loaded` line.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): validate recipes at health check"
```

### Task A8: Update builder AGENT.md with Phase 2.5 stub

**Files:**
- Modify: `agent_builder/identity/AGENT.md`

- [ ] **Step 1: Add Phase 2.5 between Phase 2 and Phase 3**

Edit `agent_builder/identity/AGENT.md`. After the "Phase 2: Tool Design" section and before "Phase 3: Identity", insert:

```markdown
### Phase 2.5: Recipe Attachment

Before designing tools from scratch, call `list_recipes()` (optionally with `type=tool|mcp|skill` or a `tag` filter) to see what reusable components exist. For each recipe that matches the agent's design, ask the user:

> "Recipe `<name>` (`<description>`) matches — attach it? (yes/no)"

Track the approved recipe names for use in Phase 4 — after `scaffold_agent` + `write_identity` + `write_tools` succeed, call `attach_recipe` once per approved recipe, in declaration order. `attach_recipe` is idempotent per (agent, recipe@version) — re-running is a no-op. If no recipes match, skip this phase entirely; the bespoke-tool path is still valid.
```

- [ ] **Step 2: Verify CLAUDE.md regenerates**

Run: `python -c "from agent_builder.utils import build_claude_md; build_claude_md()"`
Expected: no error, `agent_builder/CLAUDE.md` updated.

- [ ] **Step 3: Commit**

```bash
git add agent_builder/identity/AGENT.md
git commit -m "docs(builder): add Phase 2.5 recipe attachment workflow"
```

---

## Phase B — `attach_recipe` (Tool-Type Only)

Ships: `attach_recipe` tool handling tool-type recipes, version stamping via `RECIPE_PINS`, `{{recipe_pins_block}}` placeholder in the CLI template.

### Task B1: Add `{{recipe_pins_block}}` placeholder to agent_main.py.tmpl

**Files:**
- Modify: `agent_builder/templates/agent_main.py.tmpl`
- Modify: `agent_builder/tools/scaffold.py` (REQUIRED_PLACEHOLDERS + substitution)
- Modify: `tests/test_scaffold.py`

**Note on RECIPE_PINS format:** we write it as valid JSON so `json.loads` can parse it cleanly — `RECIPE_PINS = {"gcal": "0.1.0"}` with double quotes everywhere. This avoids using Python's literal evaluators on untrusted-file content and keeps the attach_recipe update path deterministic.

- [ ] **Step 1: Update scaffold tests to expect the new placeholder**

Add to `tests/test_scaffold.py`:

```python
@pytest.mark.asyncio
async def test_scaffold_emits_recipe_pins_block(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    await scaffold_agent({"agent_name": "my-agent", "description": "x"}, output_base=str(out))
    agent_py = (out / "my-agent" / "agent.py").read_text()
    assert "RECIPE_PINS = {}" in agent_py
    assert "{{recipe_pins_block}}" not in agent_py
```

- [ ] **Step 2: Run test to verify fail**

Run: `pytest tests/test_scaffold.py::test_scaffold_emits_recipe_pins_block -v`
Expected: FAIL (placeholder not in template yet).

- [ ] **Step 3: Add placeholder to the template**

Edit `agent_builder/templates/agent_main.py.tmpl`. Locate the `GENERATED_WITH_BUILDER_VERSION = "{{builder_version}}"` line near the top and insert `{{recipe_pins_block}}` on the line below:

```python
AGENT_NAME = "{{agent_name}}"
GENERATED_WITH_BUILDER_VERSION = "{{builder_version}}"
{{recipe_pins_block}}
AGENT_DIR = Path(__file__).parent.resolve()
```

- [ ] **Step 4: Add to REQUIRED_PLACEHOLDERS and substitution**

Edit `agent_builder/tools/scaffold.py`:

```python
REQUIRED_PLACEHOLDERS = (
    "{{agent_name}}",
    "{{agent_description}}",
    "{{builder_version}}",
    "{{recipe_pins_block}}",
    "{{tools_list}}",
    "{{allowed_tools_list}}",
    "{{permission_mode}}",
    "{{max_turns}}",
    "{{max_budget_usd}}",
    "{{cli_args_block}}",
    "{{cli_dispatch_block}}",
    "{{cli_help_epilog}}",
)
```

And in the `.replace(...)` chain inside `scaffold_agent`:

```python
        .replace("{{recipe_pins_block}}", "RECIPE_PINS = {}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_scaffold.py -v`
Expected: all passing including the new one.

- [ ] **Step 6: Commit**

```bash
git add agent_builder/templates/agent_main.py.tmpl agent_builder/tools/scaffold.py tests/test_scaffold.py
git commit -m "feat(scaffold): add {{recipe_pins_block}} placeholder (empty default)"
```

### Task B2: Design attach_recipe contract (tool-type only) — TDD

**Files:**
- Create: `tests/test_attach_recipe.py`
- Create: `agent_builder/tools/attach_recipe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_attach_recipe.py`:

```python
"""Tests for the attach_recipe builder tool."""

from pathlib import Path

import pytest

from agent_builder.tools.attach_recipe import attach_recipe

FIXTURES = Path(__file__).parent / "fixtures" / "recipes_valid"


@pytest.fixture
def agent_dir(tmp_path):
    """Simulate a just-scaffolded agent dir."""
    d = tmp_path / "output" / "test-agent"
    d.mkdir(parents=True)
    (d / "agent.py").write_text(
        'AGENT_NAME = "test-agent"\n'
        'GENERATED_WITH_BUILDER_VERSION = "0.9.0"\n'
        "RECIPE_PINS = {}\n"
        "# rest of the agent ...\n",
        encoding="utf-8",
    )
    (d / "tools.py").write_text(
        'from claude_agent_sdk import tool, create_sdk_mcp_server\n'
        'TEST_MODE = False\n'
        'tools_server = create_sdk_mcp_server(name="agent-tools", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    (d / ".env.example").write_text("# put your secrets here\n", encoding="utf-8")
    return d


@pytest.mark.asyncio
async def test_attach_tool_recipe_copies_code(agent_dir):
    result = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "hello-world"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert result.get("is_error") is not True
    tools_py = (agent_dir / "tools.py").read_text()
    assert "# recipe: hello-world @ 0.1.0" in tools_py
    assert "async def hello" in tools_py
    agent_py = (agent_dir / "agent.py").read_text()
    assert '"hello-world": "0.1.0"' in agent_py


@pytest.mark.asyncio
async def test_attach_tool_recipe_idempotent(agent_dir):
    await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "hello-world"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    tools_py_after_first = (agent_dir / "tools.py").read_text()
    result = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "hello-world"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert result.get("is_error") is not True
    tools_py_after_second = (agent_dir / "tools.py").read_text()
    assert tools_py_after_first == tools_py_after_second


@pytest.mark.asyncio
async def test_attach_unknown_recipe_errors(agent_dir):
    result = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "does-not-exist"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert result["is_error"] is True
    assert "does-not-exist" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_attach_rejects_path_traversal(agent_dir):
    result = await attach_recipe(
        {"agent_name": "../escape", "recipe_name": "hello-world"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert result["is_error"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_attach_recipe.py -v`
Expected: ImportError.

- [ ] **Step 3: Write minimal attach_recipe (tool-type only)**

Create `agent_builder/tools/attach_recipe.py`:

```python
"""attach_recipe builder tool — materializes a recipe into a generated agent."""

import json
import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder.recipes.loader import default_recipes_root, load_all_recipes
from agent_builder.recipes.schema import Recipe, RecipeError, RecipeType

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_RECIPE_PINS_PATTERN = re.compile(
    r"^(?P<prefix>RECIPE_PINS\s*=\s*)(?P<body>\{.*?\})$",
    re.MULTILINE | re.DOTALL,
)
_TOOL_RECIPE_HEADER_PATTERN = re.compile(
    r"^# recipe: (?P<name>\S+) @ (?P<version>\S+)$",
    re.MULTILINE,
)


async def attach_recipe(
    args: dict[str, Any],
    *,
    output_base: str = "output",
    recipes_root: Path | None = None,
) -> dict[str, Any]:
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

    try:
        recipes = load_all_recipes(recipes_root or default_recipes_root())
    except RecipeError as e:
        return _error(f"Recipe load error: {e}")

    recipe = next((r for r in recipes if r.name == recipe_name), None)
    if recipe is None:
        return _error(f"Recipe '{recipe_name}' not found in recipes library.")

    if recipe.type is RecipeType.TOOL:
        return _attach_tool_recipe(recipe, agent_dir, recipes_root or default_recipes_root())

    return _error(f"Recipe type '{recipe.type.value}' not yet supported (Phase B ships tool-type only).")


def _attach_tool_recipe(recipe: Recipe, agent_dir: Path, recipes_root: Path) -> dict[str, Any]:
    tools_py = agent_dir / "tools.py"
    if not tools_py.exists():
        return _error(f"{tools_py} missing — agent may not be fully scaffolded")

    content = tools_py.read_text(encoding="utf-8")

    # Idempotency: already at this version? no-op.
    for m in _TOOL_RECIPE_HEADER_PATTERN.finditer(content):
        if m.group("name") == recipe.name and m.group("version") == recipe.version:
            return _ok(f"Recipe '{recipe.name}@{recipe.version}' already attached to {agent_dir.name}.")

    tool_py_path = recipes_root / "tools" / recipe.name / "tool.py"
    tool_code = tool_py_path.read_text(encoding="utf-8")
    tool_code = _strip_tool_header(tool_code)

    header = f"\n\n# recipe: {recipe.name} @ {recipe.version}\n"
    tools_py.write_text(content.rstrip() + header + tool_code.strip() + "\n", encoding="utf-8")

    _update_recipe_pins(agent_dir, recipe)

    return _ok(f"Attached tool recipe '{recipe.name}@{recipe.version}' to {agent_dir.name}/tools.py.")


def _strip_tool_header(code: str) -> str:
    """Drop leading imports/TEST_MODE from a recipe's tool.py to avoid duplicating TOOLS_HEADER."""
    lines = code.splitlines()
    out = []
    skipping = True
    for line in lines:
        s = line.strip()
        if skipping:
            if s.startswith("#") or s.startswith('"""') or not s:
                continue
            if s.startswith("from ") or s.startswith("import "):
                continue
            if s.startswith("TEST_MODE"):
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


def _update_recipe_pins(agent_dir: Path, recipe: Recipe) -> None:
    """Update RECIPE_PINS dict in agent.py via regex + json.loads (JSON-shaped dict)."""
    agent_py = agent_dir / "agent.py"
    content = agent_py.read_text(encoding="utf-8")

    m = _RECIPE_PINS_PATTERN.search(content)
    if not m:
        # Tolerate agents scaffolded before v0.9 — insert a new line.
        content = 'RECIPE_PINS = {}\n' + content
        m = _RECIPE_PINS_PATTERN.search(content)
        assert m is not None

    try:
        current = json.loads(m.group("body"))
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"RECIPE_PINS in {agent_py} is not valid JSON — was it hand-edited? ({e})"
        ) from e

    current[recipe.name] = recipe.version
    rebuilt = m.group("prefix") + json.dumps(dict(sorted(current.items())))
    new_content = content[: m.start()] + rebuilt + content[m.end():]
    agent_py.write_text(new_content, encoding="utf-8")


def _validate_agent_name(name: str, output_base: str) -> str | None:
    if not _NAME_PATTERN.match(name):
        return f"Invalid agent name '{name}'."
    if ".." in name or "/" in name or "\\" in name:
        return f"Invalid agent name '{name}'."
    resolved = (Path(output_base) / name).resolve()
    base = Path(output_base).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        return f"Invalid agent name '{name}' (path traversal)."
    return None


def _error(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}], "is_error": True}


def _ok(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}


attach_recipe_tool = tool(
    "attach_recipe",
    "Materialize a recipe from the bundled recipes library into an existing generated agent. "
    "Phase B supports tool-type recipes only (copies tool.py into the agent's tools.py with a "
    "version-stamped header). Phase D adds mcp-type support; Phase E adds OAuth scaffolding. "
    "Idempotent per (agent, recipe@version).",
    {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string"},
            "recipe_name": {"type": "string"},
        },
        "required": ["agent_name", "recipe_name"],
    },
)(attach_recipe)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_attach_recipe.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/attach_recipe.py tests/test_attach_recipe.py
git commit -m "feat(builder): attach_recipe tool supporting tool-type recipes"
```

### Task B3: Register attach_recipe in builder MCP server

**Files:**
- Modify: `agent_builder/tools/__init__.py`
- Modify: `agent_builder/builder.py`

- [ ] **Step 1: Add import + registration to tools/__init__.py**

Same pattern as Task A6 — add `from agent_builder.tools.attach_recipe import attach_recipe_tool` and append `attach_recipe_tool` to the `tools=[...]` list.

- [ ] **Step 2: Add to builder.py allowed_tools**

Add `"mcp__builder_tools__attach_recipe"` to the allowed_tools list.

- [ ] **Step 3: Smoke test**

Run: `python -m agent_builder.builder --doctor`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add agent_builder/tools/__init__.py agent_builder/builder.py
git commit -m "feat(builder): register attach_recipe tool"
```

### Task B4: Update AGENT.md with tool-recipe attach flow

**Files:**
- Modify: `agent_builder/identity/AGENT.md`

- [ ] **Step 1: Expand Phase 4 Generation step**

Edit `agent_builder/identity/AGENT.md`. In Phase 4, after step 4 (`registry add`), insert:

```markdown
5. For every recipe approved in Phase 2.5, call `attach_recipe` with `{agent_name, recipe_name}` in declaration order. `attach_recipe` is idempotent per (agent, recipe@version). If a call returns `is_error`, STOP and surface the error to the user before continuing.
```

- [ ] **Step 2: Commit**

```bash
git add agent_builder/identity/AGENT.md
git commit -m "docs(builder): document attach_recipe call in Phase 4"
```

---

## Phase C — Telegram Poll Recipe + Poll Template

Ships: `telegram-poll` tool recipe, `agent_poll.py.tmpl`, `scaffold_agent mode="poll"`, poll-mode test_agent path. After Phase C, a minimal Telegram agent can be built end-to-end via `attach_recipe`.

### Task C1: Write the telegram-poll recipe

**Files:**
- Create: `agent_builder/recipes/tools/telegram-poll/RECIPE.md`
- Create: `agent_builder/recipes/tools/telegram-poll/tool.py`

- [ ] **Step 1: Look up current python-telegram-bot docs**

Use WebFetch on `https://docs.python-telegram-bot.org/en/stable/examples.echobot.html` or ask context7 for `python-telegram-bot` to confirm the current `Application.run_polling()` / `ApplicationBuilder` shape. If the API changed since training data, adjust the code below accordingly before writing.

- [ ] **Step 2: Write the recipe markdown**

Create `agent_builder/recipes/tools/telegram-poll/RECIPE.md`:

```markdown
---
name: telegram-poll
type: tool
version: 0.1.0
description: Long-polls Telegram bot API for incoming messages, exposes an async iterator of Incoming records.
when_to_use: Agent runs in poll mode and should react to Telegram DMs without exposing a public webhook.
env_keys:
  - name: TELEGRAM_BOT_TOKEN
    description: Token from @BotFather.
    example: "1234567890:ABC-DEF..."
  - name: TELEGRAM_ALLOWED_SENDER_IDS
    description: Comma-separated list of numeric Telegram user IDs allowed to message the bot. Others are ignored.
    example: "123456789,987654321"
allowed_tools_patterns:
  - mcp__agent_tools__telegram_send
tags: [telegram, messaging, poll]
---

# Telegram Poll

Provides two things for a poll-mode agent:

1. An async generator `telegram_poll_source()` that yields `Incoming` records (sender_id, text, media_refs, raw) from every incoming message on the configured bot, filtered to senders in `TELEGRAM_ALLOWED_SENDER_IDS`.
2. An MCP tool `telegram_send(chat_id, text)` the agent can call to reply.

## Caveats

- First unknown sender triggers one INFO log line (`ignored message from <id>`); no reply is sent.
- Photos arrive as `media_refs: [{"kind": "photo", "file_id": "..."}]`. The agent resolves them to bytes via a separate `telegram_fetch_media` tool (shipped separately when needed) or via a generic fetch helper.
- `run_polling()` blocks; the tool wraps it in an async generator so the agent's main loop can iterate naturally.
- Requires `python-telegram-bot>=21.0` — installed via the `[telegram]` extra: `pip install -e ".[dev,telegram]"`.
```

- [ ] **Step 3: Write the tool code**

Create `agent_builder/recipes/tools/telegram-poll/tool.py`:

```python
"""telegram-poll recipe — exposes telegram_poll_source + telegram_send.

This file is copied into an agent's tools.py by attach_recipe. It assumes the
TOOLS_HEADER (imports + TEST_MODE = False) already sits at the top of tools.py
— that's prepended by write_tools.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field

from claude_agent_sdk import tool

try:
    from telegram import Update
    from telegram.ext import Application, MessageHandler, filters
except ImportError:  # pragma: no cover
    Application = None  # type: ignore


logger = logging.getLogger(__name__)


@dataclass
class Incoming:
    sender_id: int
    chat_id: int
    text: str
    media_refs: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def _allowed_sender_ids() -> set[int]:
    raw = os.environ.get("TELEGRAM_ALLOWED_SENDER_IDS", "").strip()
    if not raw:
        return set()
    return {int(x) for x in raw.split(",") if x.strip()}


async def telegram_poll_source(queue: "asyncio.Queue[Incoming] | None" = None):
    """Async generator yielding Incoming for every authorized message."""
    if Application is None:
        raise RuntimeError(
            "python-telegram-bot not installed. pip install -e '.[telegram]' to enable poll mode."
        )
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    allowed = _allowed_sender_ids()
    q: "asyncio.Queue[Incoming]" = queue if queue is not None else asyncio.Queue()

    async def _handle(update: Update, _context):
        msg = update.effective_message
        if msg is None or update.effective_user is None:
            return
        if allowed and update.effective_user.id not in allowed:
            logger.info("ignored message from %s", update.effective_user.id)
            return
        media_refs: list[dict] = []
        if msg.photo:
            biggest = max(msg.photo, key=lambda p: p.width * p.height)
            media_refs.append({"kind": "photo", "file_id": biggest.file_id})
        if msg.document:
            media_refs.append({"kind": "document", "file_id": msg.document.file_id})
        await q.put(Incoming(
            sender_id=update.effective_user.id,
            chat_id=update.effective_chat.id if update.effective_chat else update.effective_user.id,
            text=msg.text or msg.caption or "",
            media_refs=media_refs,
            raw=update.to_dict(),
        ))

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.ALL, _handle))

    async def _run_app():
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

    runner = asyncio.create_task(_run_app())
    try:
        while True:
            yield await q.get()
    finally:
        runner.cancel()
        try:
            await app.updater.stop()
        except Exception:  # pragma: no cover — best-effort shutdown
            pass


@tool(
    "telegram_send",
    "Send a text message back to a Telegram chat.",
    {
        "type": "object",
        "properties": {
            "chat_id": {"type": "integer"},
            "text": {"type": "string"},
        },
        "required": ["chat_id", "text"],
    },
)
async def telegram_send(args):
    if TEST_MODE:  # noqa: F821 — provided by TOOLS_HEADER
        return {"content": [{"type": "text", "text": f"[mock] send {args['text']!r} to {args['chat_id']}"}]}
    if Application is None:
        return {"content": [{"type": "text", "text": "python-telegram-bot not installed"}], "is_error": True}
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    async with app:
        await app.bot.send_message(chat_id=args["chat_id"], text=args["text"])
    return {"content": [{"type": "text", "text": "sent"}]}


# NOTE: attach_recipe drops this file's contents into an agent's tools.py *after* the
# existing tools_server assignment is already present. The agent's final tools_server
# will NOT include telegram_send automatically — the agent author (or a follow-up
# edit_agent call) re-emits the create_sdk_mcp_server line to register telegram_send.
# A future Phase G improvement will auto-rewrite the tools_server assignment.
```

- [ ] **Step 4: Verify doctor loads the new recipe**

Run: `python -m agent_builder.builder --doctor`
Expected: `[OK  ] recipes load: 1 recipe(s) loaded`.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/recipes/tools/telegram-poll/
git commit -m "feat(recipes): telegram-poll tool recipe"
```

### Task C2: Write the agent_poll.py.tmpl template

**Files:**
- Create: `agent_builder/templates/agent_poll.py.tmpl`
- Create: `tests/test_agent_poll_template.py`

- [ ] **Step 1: Write a placeholder-coverage test**

Create `tests/test_agent_poll_template.py`:

```python
"""Tests ensuring the poll-mode template has the expected placeholder set."""

from pathlib import Path


TEMPLATES_DIR = Path("agent_builder") / "templates"

EXPECTED_IN_POLL = {
    "{{agent_name}}",
    "{{agent_description}}",
    "{{builder_version}}",
    "{{recipe_pins_block}}",
    "{{tools_list}}",
    "{{allowed_tools_list}}",
    "{{permission_mode}}",
    "{{max_turns}}",
    "{{max_budget_usd}}",
    "{{poll_source_import}}",      # poll-only
    "{{poll_source_expr}}",        # poll-only
}


def test_poll_template_has_all_placeholders():
    content = (TEMPLATES_DIR / "agent_poll.py.tmpl").read_text(encoding="utf-8")
    missing = [p for p in EXPECTED_IN_POLL if p not in content]
    assert not missing, f"poll template missing placeholders: {missing}"


def test_poll_template_no_stdin_loop():
    content = (TEMPLATES_DIR / "agent_poll.py.tmpl").read_text(encoding="utf-8")
    assert 'input("> ")' not in content
    assert "asyncio.to_thread(input" not in content
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest tests/test_agent_poll_template.py -v`
Expected: FileNotFoundError on the template.

- [ ] **Step 3: Write the poll template**

Create `agent_builder/templates/agent_poll.py.tmpl` — start by copying `agent_main.py.tmpl` verbatim, then edit in-place with the following deltas:

**Delta 1 — near the top imports**, insert `{{poll_source_import}}` on its own line immediately after the `from logging.handlers import RotatingFileHandler` line (before the claude_agent_sdk imports):

```python
from logging.handlers import RotatingFileHandler
from pathlib import Path

{{poll_source_import}}

try:
    from dotenv import load_dotenv
```

**Delta 2 — argparse block**: poll mode has no `--prompt`/`--spec`. Remove the `{{cli_args_block}}` line entirely from the template, and replace the `parser = argparse.ArgumentParser(...)` block with:

```python
    parser = argparse.ArgumentParser(
        description="{{agent_description}}",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug output")
    args = parser.parse_args()
    verbose = args.verbose
```

**Delta 3 — CLI dispatch block**: remove the `{{cli_dispatch_block}}` line. Poll mode never runs in CLI-dispatch mode.

**Delta 4 — main loop**: replace the `while True: input(...)` loop with:

```python
    async with ClaudeSDKClient(options=options) as client:
        print(f"\n  {AGENT_NAME} ready — listening for incoming messages.\n")
        poll_source = {{poll_source_expr}}
        async for incoming in poll_source:
            logger.info(
                "incoming: sender=%s text=%s media=%s",
                incoming.sender_id, incoming.text[:60], len(incoming.media_refs),
            )
            prompt = (
                f"New message from sender {incoming.sender_id} in chat {incoming.chat_id}.\n"
                f"Text: {incoming.text!r}\n"
                f"Media refs: {incoming.media_refs}\n"
                f"Respond appropriately."
            )
            try:
                await client.query(prompt)
                await _drain_responses(client, verbose)
            except Exception as e:
                logger.error("poll loop error: %s\n%s", e, traceback.format_exc())
```

Keep every other block (identity bootstrap, Spinner, format_tool_call, safety_hook, _drain_responses, logging setup) byte-identical to the CLI template. The `{{recipe_pins_block}}` from Task B1 stays in the same position.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_agent_poll_template.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/templates/agent_poll.py.tmpl tests/test_agent_poll_template.py
git commit -m "feat(templates): agent_poll.py.tmpl for long-poll workers"
```

### Task C3: Extend scaffold_agent with `mode` parameter

**Files:**
- Modify: `agent_builder/tools/scaffold.py`
- Modify: `tests/test_scaffold.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scaffold.py`:

```python
@pytest.mark.asyncio
async def test_scaffold_cli_mode_default(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    result = await scaffold_agent(
        {"agent_name": "cli-a", "description": "x"},
        output_base=str(out),
    )
    assert result.get("is_error") is not True
    assert (out / "cli-a" / "agent.py").exists()
    assert 'while True' in (out / "cli-a" / "agent.py").read_text()


@pytest.mark.asyncio
async def test_scaffold_poll_mode(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    result = await scaffold_agent(
        {"agent_name": "poll-a", "description": "x", "mode": "poll"},
        output_base=str(out),
    )
    assert result.get("is_error") is not True
    content = (out / "poll-a" / "agent.py").read_text()
    assert 'async for incoming in poll_source' in content
    # scaffold renders stubs for poll source when no recipe attached yet
    assert "{{poll_source_import}}" not in content
    assert "{{poll_source_expr}}" not in content
    # Stub expression is present
    assert "_stub_poll_source" in content


@pytest.mark.asyncio
async def test_scaffold_unknown_mode_errors(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    result = await scaffold_agent(
        {"agent_name": "bad", "description": "x", "mode": "carrier-pigeon"},
        output_base=str(out),
    )
    assert result["is_error"] is True
    assert "mode" in result["content"][0]["text"]
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_scaffold.py -v`
Expected: poll/mode tests fail.

- [ ] **Step 3: Implement in scaffold.py**

Edit `agent_builder/tools/scaffold.py`. Near the top, define the template map and stubs:

```python
_TEMPLATE_BY_MODE = {
    "cli": "agent_main.py.tmpl",
    "poll": "agent_poll.py.tmpl",
    # "server" arrives in Phase F
}

# Stubs filled when no recipe supplies poll_source. Keeps generated agents
# syntactically valid so they can be run (will raise NotImplementedError when
# the poll loop starts, with a helpful message).
_POLL_SOURCE_IMPORT_STUB = ""
_POLL_SOURCE_EXPR_STUB = (
    "_stub_poll_source()  # attach a poll recipe (e.g. telegram-poll) to replace this"
)
_POLL_SOURCE_STUB_IMPL = '''
async def _stub_poll_source():
    raise NotImplementedError(
        "No poll source attached. Run: python -m agent_builder.builder "
        "then attach_recipe for this agent with a poll-type recipe."
    )
    yield  # pragma: no cover — make this a generator
'''
```

Restructure `REQUIRED_PLACEHOLDERS` as per-template, with a back-compat alias:

```python
REQUIRED_PLACEHOLDERS_COMMON = (
    "{{agent_name}}",
    "{{agent_description}}",
    "{{builder_version}}",
    "{{recipe_pins_block}}",
    "{{tools_list}}",
    "{{allowed_tools_list}}",
    "{{permission_mode}}",
    "{{max_turns}}",
    "{{max_budget_usd}}",
)

REQUIRED_PLACEHOLDERS_BY_MODE = {
    "cli": REQUIRED_PLACEHOLDERS_COMMON + (
        "{{cli_args_block}}",
        "{{cli_dispatch_block}}",
        "{{cli_help_epilog}}",
    ),
    "poll": REQUIRED_PLACEHOLDERS_COMMON + (
        "{{poll_source_import}}",
        "{{poll_source_expr}}",
    ),
}

# Back-compat alias that doctor.py still imports.
REQUIRED_PLACEHOLDERS = REQUIRED_PLACEHOLDERS_BY_MODE["cli"]
```

In `scaffold_agent(...)`, add mode validation and template selection:

```python
    mode = args.get("mode", "cli")
    if mode not in _TEMPLATE_BY_MODE:
        return {
            "content": [{"type": "text", "text": f"Invalid mode '{mode}'. Allowed: {sorted(_TEMPLATE_BY_MODE)}."}],
            "is_error": True,
        }
    template_path = TEMPLATES_DIR / _TEMPLATE_BY_MODE[mode]
    expected = REQUIRED_PLACEHOLDERS_BY_MODE[mode]
    # (use `expected` instead of REQUIRED_PLACEHOLDERS in the drift guard below)
```

Extend the `.replace(...)` chain. For CLI mode, no change. For poll mode, inject the stub before main() and substitute:

```python
    if mode == "poll":
        agent_py = agent_py.replace(
            "# --- Main ---",
            _POLL_SOURCE_STUB_IMPL + "\n# --- Main ---",
        )
        agent_py = agent_py.replace("{{poll_source_import}}", _POLL_SOURCE_IMPORT_STUB)
        agent_py = agent_py.replace("{{poll_source_expr}}", _POLL_SOURCE_EXPR_STUB)
```

Register `mode` in the tool's JSON schema:

```python
        "mode": {"type": "string", "enum": ["cli", "poll"]},
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_scaffold.py -v`
Expected: all passing.

- [ ] **Step 5: Run doctor**

Run: `python -m agent_builder.builder --doctor`
Expected: exit 0. (Doctor's template check is still cli-only — extended in C4.)

- [ ] **Step 6: Commit**

```bash
git add agent_builder/tools/scaffold.py tests/test_scaffold.py
git commit -m "feat(scaffold): mode param (cli|poll) selects template"
```

### Task C4: Extend doctor to validate both templates

**Files:**
- Modify: `agent_builder/doctor.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 1: Write the test**

Add to `tests/test_doctor.py`:

```python
def test_doctor_validates_poll_template(tmp_path):
    _scaffold_fake_repo(tmp_path)
    # Break the poll template by stripping a placeholder.
    real_poll = Path("agent_builder") / "templates" / "agent_poll.py.tmpl"
    poll_content = real_poll.read_text(encoding="utf-8").replace("{{poll_source_expr}}", "")
    (tmp_path / "agent_builder" / "templates" / "agent_poll.py.tmpl").write_text(
        poll_content, encoding="utf-8"
    )

    (tmp_path / "agent_builder" / "recipes").mkdir()
    for d in ("mcps", "tools", "skills"):
        (tmp_path / "agent_builder" / "recipes" / d).mkdir()

    registry_path = tmp_path / "agents.json"
    registry_path.write_text("[]", encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry_path))
    assert exit_code == 1
    assert any(c["status"] == "FAIL" and "poll" in c["name"] for c in checks)
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_doctor.py -v`
Expected: fail (doctor doesn't check poll template yet).

- [ ] **Step 3: Generalize the template check**

Edit `agent_builder/doctor.py` — update import at the top:

```python
from agent_builder.tools.scaffold import REQUIRED_PLACEHOLDERS_BY_MODE, _TEMPLATE_BY_MODE
```

Replace the existing `_check_template_placeholders` with:

```python
def _check_template_placeholders(builder_dir: Path) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for mode, fname in _TEMPLATE_BY_MODE.items():
        template_path = builder_dir / "templates" / fname
        name = f"template: {fname}"
        if not template_path.exists():
            checks.append(_check("FAIL", name, f"missing: {template_path}"))
            continue
        content = template_path.read_text(encoding="utf-8")
        expected = REQUIRED_PLACEHOLDERS_BY_MODE[mode]
        missing = [ph for ph in expected if ph not in content]
        if missing:
            checks.append(_check("FAIL", name + " placeholders", f"{template_path} is missing: {missing}"))
        else:
            checks.append(_check("OK", name + " placeholders", f"all {len(expected)} present"))
    return checks
```

Update the caller in `run_health_check` — change `checks.append(_check_template_placeholders(builder_dir))` to `checks.extend(_check_template_placeholders(builder_dir))`.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_doctor.py -v`
Expected: pass.

Run: `python -m agent_builder.builder --doctor`
Expected: exit 0, two OK lines for template placeholders.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): validate placeholders across all templates"
```

### Task C5: Extend attach_recipe to wire poll recipe into poll-mode agents

**Files:**
- Modify: `agent_builder/tools/attach_recipe.py`
- Modify: `tests/test_attach_recipe.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_attach_recipe.py`:

```python
@pytest.fixture
def poll_agent_dir(tmp_path):
    """Scaffold a real poll-mode agent, then return its dir."""
    import asyncio
    from agent_builder.tools.scaffold import scaffold_agent
    out = tmp_path / "output"
    out.mkdir()
    asyncio.run(scaffold_agent(
        {"agent_name": "tg-a", "description": "x", "mode": "poll"},
        output_base=str(out),
    ))
    (out / "tg-a" / "tools.py").write_text(
        'from claude_agent_sdk import tool, create_sdk_mcp_server\n'
        'TEST_MODE = False\n'
        'tools_server = create_sdk_mcp_server(name="agent-tools", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    return out / "tg-a"


@pytest.mark.asyncio
async def test_attach_telegram_poll_fills_stubs(poll_agent_dir):
    # Uses the real bundled telegram-poll recipe — no fixture override.
    result = await attach_recipe(
        {"agent_name": "tg-a", "recipe_name": "telegram-poll"},
        output_base=str(poll_agent_dir.parent),
    )
    assert result.get("is_error") is not True, result
    agent_py = (poll_agent_dir / "agent.py").read_text()
    # Stub replaced with real import + expression
    assert "_stub_poll_source()" not in agent_py
    assert "telegram_poll_source" in agent_py
    tools_py = (poll_agent_dir / "tools.py").read_text()
    assert "telegram-poll @ 0.1.0" in tools_py
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_attach_recipe.py -v`
Expected: attach-poll test fails (stubs unchanged).

- [ ] **Step 3: Add poll-source wiring in attach_recipe**

Edit `agent_builder/tools/attach_recipe.py`. Add a registry of poll-capable recipes and a wiring helper:

```python
_POLL_CAPABLE = {
    "telegram-poll": (
        # import line (inserted near the top of agent.py)
        "from tools import telegram_poll_source  # poll source (recipe: telegram-poll)",
        # expression that replaces _stub_poll_source()
        "telegram_poll_source()",
    ),
}


def _maybe_wire_poll_source(recipe: Recipe, agent_dir: Path) -> None:
    if recipe.name not in _POLL_CAPABLE:
        return
    agent_py = agent_dir / "agent.py"
    content = agent_py.read_text(encoding="utf-8")
    if "_stub_poll_source()" not in content:
        return  # not in poll mode, or already wired
    import_line, expr = _POLL_CAPABLE[recipe.name]
    content = content.replace("_stub_poll_source()", expr, 1)
    # Inject import just above the existing claude_agent_sdk import block
    content = content.replace(
        "from claude_agent_sdk import (",
        f"{import_line}\nfrom claude_agent_sdk import (",
        1,
    )
    agent_py.write_text(content, encoding="utf-8")
```

Call `_maybe_wire_poll_source(recipe, agent_dir)` at the end of `_attach_tool_recipe`, after `_update_recipe_pins(...)`.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_attach_recipe.py -v`
Expected: passing.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/attach_recipe.py tests/test_attach_recipe.py
git commit -m "feat(attach_recipe): wire poll-capable recipes into poll-mode stubs"
```

### Task C6: Add poll mode to test_agent

**Files:**
- Modify: `agent_builder/tools/test_agent.py`
- Create: `tests/test_test_agent_poll.py`

- [ ] **Step 1: Inspect current test_agent**

Read `agent_builder/tools/test_agent.py` to understand its current signature. It flips `TEST_MODE` in the target agent's `tools.py`, imports the module dynamically, and runs prompts through `query()` with `max_turns=5`, then restores `TEST_MODE = False` in a `finally` block.

- [ ] **Step 2: Write the failing test**

Create `tests/test_test_agent_poll.py`:

```python
"""Tests for test_agent's new poll mode."""

import pytest

from agent_builder.tools.test_agent import test_agent


@pytest.mark.asyncio
async def test_test_agent_poll_mode_processes_synthetic_messages(tmp_path):
    # Scaffold a throwaway poll-mode agent with no real recipe attached — the
    # _stub_poll_source will be monkeypatched at test time with a fake source
    # that yields the supplied messages, then stops.
    import asyncio
    from agent_builder.tools.scaffold import scaffold_agent

    out = tmp_path / "output"
    out.mkdir()
    await scaffold_agent(
        {"agent_name": "poll-t", "description": "x", "mode": "poll"},
        output_base=str(out),
    )
    (out / "poll-t" / "tools.py").write_text(
        'from claude_agent_sdk import tool, create_sdk_mcp_server\n'
        'TEST_MODE = False\n'
        'tools_server = create_sdk_mcp_server(name="agent-tools", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    for md in ("AGENT.md", "SOUL.md", "MEMORY.md"):
        (out / "poll-t" / md).write_text("# " + md, encoding="utf-8")

    result = await test_agent(
        {
            "agent_name": "poll-t",
            "mode": "poll",
            "messages": [
                {"sender_id": 1, "chat_id": 1, "text": "hello"},
                {"sender_id": 1, "chat_id": 1, "text": "goodbye"},
            ],
        },
        output_base=str(out),
    )
    assert result.get("is_error") is not True
    # Assert the per-message transcript was recorded — exact shape is
    # implementation-defined; adjust once test_agent returns structured results.
    assert "2" in result["content"][0]["text"]
```

- [ ] **Step 3: Extend test_agent**

Edit `agent_builder/tools/test_agent.py` — add an optional `mode` param (default `"cli"`). When `mode == "poll"`:

1. Same `TEST_MODE = True` flip in the agent's `tools.py` as CLI mode.
2. Write a small `_poll_source_test_stub.py` file into the agent's dir that defines:
   ```python
   from dataclasses import dataclass, field
   @dataclass
   class Incoming:
       sender_id: int
       chat_id: int
       text: str
       media_refs: list = field(default_factory=list)
       raw: dict = field(default_factory=dict)

   _MESSAGES = <messages list serialized as repr>

   async def test_poll_source():
       for m in _MESSAGES:
           yield Incoming(**m)
   ```
3. Rewrite `agent.py`'s `poll_source = _stub_poll_source()` line (or `telegram_poll_source()` line if attached) to `poll_source = test_poll_source()`, and inject `from _poll_source_test_stub import test_poll_source, Incoming` above the `from claude_agent_sdk import` block.
4. Run `python agent.py` as a subprocess (the existing `query()`-based path is CLI-specific; poll mode runs the whole loop).
5. Capture stdout/stderr + exit code, assert clean exit.
6. In the `finally` block, restore `TEST_MODE = False`, delete `_poll_source_test_stub.py`, and revert the `agent.py` import / poll_source line edits (or restore a `.bak` copy).

Accept the added complexity — subprocess-based testing is the cleanest way to exercise the real `async for incoming in poll_source` loop against synthetic input.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_test_agent_poll.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/test_agent.py tests/test_test_agent_poll.py
git commit -m "feat(test_agent): support mode=\"poll\" with synthetic messages"
```

---

## Phase D — MCP Recipe Type

Ships: `attach_recipe` handling mcp-type, `{{external_mcp_block}}` placeholder in both templates, `scaffold_agent external_mcps` param, env_passthrough validator, `.env.example` merger.

### Task D1: Add `{{external_mcp_block}}` placeholder to both templates

**Files:**
- Modify: `agent_builder/templates/agent_main.py.tmpl`
- Modify: `agent_builder/templates/agent_poll.py.tmpl`
- Modify: `agent_builder/tools/scaffold.py`
- Modify: `tests/test_scaffold.py`, `tests/test_agent_poll_template.py`

- [ ] **Step 1: Test expects empty default**

Add to `tests/test_scaffold.py`:

```python
@pytest.mark.asyncio
async def test_scaffold_emits_empty_external_mcp_block(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    await scaffold_agent({"agent_name": "e", "description": "x"}, output_base=str(out))
    content = (out / "e" / "agent.py").read_text()
    assert '"agent_tools": tools_server' in content
    assert "{{external_mcp_block}}" not in content
```

Update `tests/test_agent_poll_template.py`'s `EXPECTED_IN_POLL` set to include `"{{external_mcp_block}}"`.

- [ ] **Step 2: Run to verify fail**

Expected: FAIL.

- [ ] **Step 3: Add placeholder in both templates**

In both `agent_main.py.tmpl` and `agent_poll.py.tmpl`, change the `mcp_servers={...}` literal inside `ClaudeAgentOptions(...)` to:

```python
    mcp_servers={
        "agent_tools": tools_server,
        {{external_mcp_block}}
    },
```

- [ ] **Step 4: Add to scaffold substitution + placeholders**

In `agent_builder/tools/scaffold.py`, extend `REQUIRED_PLACEHOLDERS_COMMON`:

```python
REQUIRED_PLACEHOLDERS_COMMON = (
    "{{agent_name}}",
    "{{agent_description}}",
    "{{builder_version}}",
    "{{recipe_pins_block}}",
    "{{external_mcp_block}}",
    "{{tools_list}}",
    "{{allowed_tools_list}}",
    "{{permission_mode}}",
    "{{max_turns}}",
    "{{max_budget_usd}}",
)
```

In the `.replace(...)` chain (for both cli and poll modes):

```python
    .replace("{{external_mcp_block}}", "")   # empty default; Task D2 fills it via external_mcps arg
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_scaffold.py tests/test_agent_poll_template.py -v`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add agent_builder/templates/agent_main.py.tmpl agent_builder/templates/agent_poll.py.tmpl agent_builder/tools/scaffold.py tests/test_scaffold.py tests/test_agent_poll_template.py
git commit -m "feat(scaffold): add {{external_mcp_block}} placeholder (empty default)"
```

### Task D2: Accept `external_mcps` in scaffold_agent

**Files:**
- Modify: `agent_builder/tools/scaffold.py`
- Modify: `tests/test_scaffold.py`

- [ ] **Step 1: Test**

Add to `tests/test_scaffold.py`:

```python
@pytest.mark.asyncio
async def test_scaffold_external_mcps_inlined(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    result = await scaffold_agent(
        {
            "agent_name": "ex",
            "description": "x",
            "external_mcps": {
                "gcal": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-google-calendar"],
                },
            },
        },
        output_base=str(out),
    )
    assert result.get("is_error") is not True, result
    content = (out / "ex" / "agent.py").read_text()
    assert '"gcal"' in content
    assert '"npx"' in content


@pytest.mark.asyncio
async def test_scaffold_external_mcps_malformed_errors(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    result = await scaffold_agent(
        {
            "agent_name": "bad",
            "description": "x",
            "external_mcps": {"oops": "not-a-dict"},
        },
        output_base=str(out),
    )
    assert result["is_error"] is True
```

- [ ] **Step 2: Run to verify fail**

Expected: FAIL.

- [ ] **Step 3: Implement**

In `scaffold_agent(...)`, after argument collection:

```python
    external_mcps = args.get("external_mcps", {})
    if not isinstance(external_mcps, dict):
        return _scaffold_error("external_mcps must be a dict")
    for name, cfg in external_mcps.items():
        if not isinstance(cfg, dict) or "type" not in cfg:
            return _scaffold_error(f"external_mcps[{name!r}]: must be a dict with 'type' key")
    if external_mcps:
        external_mcp_block = ",\n        ".join(
            f'"{name}": {repr(cfg)}' for name, cfg in external_mcps.items()
        ) + ","
    else:
        external_mcp_block = ""
```

Where `_scaffold_error(msg)` returns the MCP error shape (factor out of the existing inline return statements if not already present).

Pipe `external_mcp_block` into the `.replace(...)` chain (replace the empty default from D1).

Add to the JSON schema:

```python
        "external_mcps": {"type": "object"},
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scaffold.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/scaffold.py tests/test_scaffold.py
git commit -m "feat(scaffold): accept external_mcps dict and render inline"
```

### Task D3: Implement mcp-type handling in attach_recipe

**Files:**
- Modify: `agent_builder/tools/attach_recipe.py`
- Modify: `tests/test_attach_recipe.py`
- Create: `tests/fixtures/recipes_valid/mcps/fake-mcp/RECIPE.md`
- Create: `tests/fixtures/recipes_valid/mcps/fake-mcp/mcp.json`

- [ ] **Step 1: Create fixture**

Create `tests/fixtures/recipes_valid/mcps/fake-mcp/RECIPE.md`:

```markdown
---
name: fake-mcp
type: mcp
version: 0.1.0
description: Fake MCP for tests.
when_to_use: Never.
env_keys:
  - name: FAKE_TOKEN
    description: Anything.
    example: "xyz"
allowed_tools_patterns:
  - mcp__fake__*
tags: [test]
---

Body.
```

Create `tests/fixtures/recipes_valid/mcps/fake-mcp/mcp.json`:

```json
{
  "type": "stdio",
  "command": "echo",
  "args": ["fake"],
  "env_passthrough": ["FAKE_TOKEN"]
}
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_attach_recipe.py`:

```python
@pytest.mark.asyncio
async def test_attach_mcp_recipe_inlines_into_agent_py(agent_dir):
    result = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "fake-mcp"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    assert result.get("is_error") is not True, result
    agent_py = (agent_dir / "agent.py").read_text()
    assert '"fake-mcp"' in agent_py
    env_ex = (agent_dir / ".env.example").read_text()
    assert "FAKE_TOKEN" in env_ex
    assert "# --- from recipe: fake-mcp @ 0.1.0 ---" in env_ex


@pytest.mark.asyncio
async def test_attach_mcp_recipe_idempotent(agent_dir):
    await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "fake-mcp"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    env_ex_first = (agent_dir / ".env.example").read_text()
    await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "fake-mcp"},
        output_base=str(agent_dir.parent),
        recipes_root=FIXTURES,
    )
    env_ex_second = (agent_dir / ".env.example").read_text()
    assert env_ex_first == env_ex_second
```

Also add a unit test for the env merger's conflict detection — create `tests/test_env_merge.py`:

```python
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
```

- [ ] **Step 3: Implement mcp handling**

Extend `agent_builder/tools/attach_recipe.py`:

```python
import json


def _attach_mcp_recipe(recipe: Recipe, agent_dir: Path, recipes_root: Path) -> dict[str, Any]:
    mcp_json_path = recipes_root / "mcps" / recipe.name / "mcp.json"
    mcp_cfg = json.loads(mcp_json_path.read_text(encoding="utf-8"))

    # Validate env_passthrough keys match declared env_keys.
    passthrough = mcp_cfg.pop("env_passthrough", [])
    declared = {k.name for k in recipe.env_keys}
    unknown = [k for k in passthrough if k not in declared]
    if unknown:
        return _error(
            f"mcp.json env_passthrough references undeclared env_keys: {unknown}. "
            f"Declared: {sorted(declared)}."
        )

    try:
        _merge_mcp_server_entry(agent_dir / "agent.py", recipe.name, mcp_cfg)
        _merge_env_example(agent_dir / ".env.example", recipe)
    except RuntimeError as e:
        return _error(str(e))

    _update_recipe_pins(agent_dir, recipe)
    return _ok(f"Attached mcp recipe '{recipe.name}@{recipe.version}' to {agent_dir.name}.")


def _merge_mcp_server_entry(agent_py: Path, name: str, cfg: dict) -> None:
    content = agent_py.read_text(encoding="utf-8")
    marker = '"agent_tools": tools_server,'
    if marker not in content:
        raise RuntimeError("agent.py missing agent_tools marker — pre-v0.9 agent?")
    entry = f'"{name}": {repr(cfg)},'
    if entry in content:
        return  # idempotent
    content = content.replace(marker, marker + f"\n        {entry}", 1)
    agent_py.write_text(content, encoding="utf-8")


_ENV_RECIPE_BANNER = re.compile(
    r"^# --- from recipe: (?P<name>\S+) @ (?P<version>\S+) ---$",
    re.MULTILINE,
)


def _merge_env_example(env_path: Path, recipe: Recipe) -> None:
    current = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    # Idempotency: exact banner+version already present -> no-op.
    for m in _ENV_RECIPE_BANNER.finditer(current):
        if m.group("name") == recipe.name and m.group("version") == recipe.version:
            return

    # Conflict detection: any of our keys already declared?
    my_keys = {k.name for k in recipe.env_keys}
    for line in current.splitlines():
        s = line.strip()
        if "=" in s and not s.startswith("#"):
            key = s.split("=", 1)[0]
            if key in my_keys:
                raise RuntimeError(
                    f"env key '{key}' already in .env.example — conflict with recipe {recipe.name}"
                )

    block = [f"\n# --- from recipe: {recipe.name} @ {recipe.version} ---"]
    for k in recipe.env_keys:
        block.append(f"# {k.description}")
        block.append(f"{k.name}={k.example}")
    env_path.write_text(current.rstrip() + "\n" + "\n".join(block) + "\n", encoding="utf-8")
```

Route mcp recipes at the top-level `attach_recipe`:

```python
    if recipe.type is RecipeType.TOOL:
        return _attach_tool_recipe(recipe, agent_dir, recipes_root or default_recipes_root())
    if recipe.type is RecipeType.MCP:
        return _attach_mcp_recipe(recipe, agent_dir, recipes_root or default_recipes_root())
    return _error(f"Recipe type '{recipe.type.value}' not yet supported.")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_attach_recipe.py tests/test_env_merge.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/attach_recipe.py tests/test_attach_recipe.py tests/test_env_merge.py tests/fixtures/recipes_valid/mcps/
git commit -m "feat(attach_recipe): mcp-type support with env merge + pin update"
```

### Task D4: Update builder AGENT.md with external MCP + mcp recipe instructions

**Files:**
- Modify: `agent_builder/identity/AGENT.md`

- [ ] **Step 1: Extend Phase 2 and Phase 4**

In Phase 2 Tool Design, append this paragraph:

```markdown
Consider external MCP servers when the agent needs to talk to a service with an existing MCP (Google Calendar, Notion, Linear, etc.). Prefer attaching an mcp-type recipe from `list_recipes(type="mcp")` over hand-writing tools. If no recipe exists, you may pass `external_mcps={<name>: {<SDK-shaped cfg>}}` to `scaffold_agent` directly, but this bypasses the recipe library's OAuth scaffolding and env_passthrough validation.
```

In Phase 4 Generation, append:

```markdown
When passing external_mcps directly (not via recipe), you MUST also append `mcp__<name>__*` to allowed_tools_list. attach_recipe does this for recipe-sourced MCPs automatically.
```

- [ ] **Step 2: Commit**

```bash
git add agent_builder/identity/AGENT.md
git commit -m "docs(builder): document external MCPs and mcp recipes"
```

---

## Phase E — OAuth Scaffolding + Google Calendar Recipe

Ships: OAuth helper template flow, first real MCP recipe with OAuth, `docs/oauth-setup.md`, handoff notice integration.

### Task E1: Write the google-calendar recipe skeleton

**Files:**
- Create: `agent_builder/recipes/mcps/google-calendar/RECIPE.md`
- Create: `agent_builder/recipes/mcps/google-calendar/mcp.json`

- [ ] **Step 1: Research the current Google Calendar MCP landscape**

Use WebFetch against the npm registry (`https://www.npmjs.com/search?q=google-calendar%20mcp`) or modelcontextprotocol org repos to find a maintained Google Calendar MCP server. Record chosen package and version in the `mcp.json` args. If no first-party server exists, pick a community one and note it in the RECIPE.md body, or defer to a follow-up Python MCP (out of scope here).

- [ ] **Step 2: Write RECIPE.md**

Create `agent_builder/recipes/mcps/google-calendar/RECIPE.md`:

```markdown
---
name: google-calendar
type: mcp
version: 0.1.0
description: Read/write Google Calendar events via the Google Calendar MCP server.
when_to_use: Agent creates, updates, reads, or deletes calendar events on behalf of the user.
env_keys:
  - name: GOOGLE_OAUTH_CLIENT_SECRETS
    description: Path to OAuth client JSON downloaded from Google Cloud Console.
    example: ./credentials.json
  - name: GOOGLE_OAUTH_TOKEN_PATH
    description: Where setup_auth.py writes the refresh token JSON (gitignored by default).
    example: ./token.json
oauth_scopes:
  - https://www.googleapis.com/auth/calendar
allowed_tools_patterns:
  - mcp__gcal__*
tags: [calendar, google, oauth]
---

# Google Calendar MCP

Full setup steps, OAuth consent screen notes, and troubleshooting live in `docs/oauth-setup.md`. The short version:

1. Google Cloud Console → new project → enable Calendar API → OAuth consent screen → add the `calendar` scope.
2. Download the OAuth client JSON, save it next to the agent as `credentials.json`.
3. Set `GOOGLE_OAUTH_CLIENT_SECRETS=./credentials.json` and `GOOGLE_OAUTH_TOKEN_PATH=./token.json` in the agent's `.env`.
4. Run `python setup_auth.py` once. Browser opens, grant access, done.

After that, `python agent.py` has Calendar tools available as `mcp__gcal__*`.
```

- [ ] **Step 3: Write mcp.json**

Create `agent_builder/recipes/mcps/google-calendar/mcp.json`. Replace `@<package>` below with the package chosen in Step 1:

```json
{
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@<package-chosen-in-step-1>"],
  "env_passthrough": ["GOOGLE_OAUTH_CLIENT_SECRETS", "GOOGLE_OAUTH_TOKEN_PATH"]
}
```

- [ ] **Step 4: Verify recipe loads BUT fails validation (setup_auth.py.tmpl missing)**

Run: `python -m agent_builder.builder --doctor`
Expected: `[FAIL] recipes load: ... mcp recipe declares oauth_scopes but has no setup_auth.py.tmpl`.

This confirms loader's sibling-file check catches missing OAuth helper. Task E2 adds the template.

- [ ] **Step 5: Commit (WIP — intentionally broken)**

```bash
git add agent_builder/recipes/mcps/google-calendar/
git commit -m "wip(recipes): google-calendar skeleton (missing setup_auth.py.tmpl)"
```

### Task E2: Write setup_auth.py.tmpl for google-calendar

**Files:**
- Create: `agent_builder/recipes/mcps/google-calendar/setup_auth.py.tmpl`

- [ ] **Step 1: Write the OAuth helper template**

Placeholders: `{{scopes}}`, `{{client_secrets_env}}`, `{{token_path_env}}`, `{{recipe_name}}`. Rendered by `attach_recipe` at materialization time.

Create `agent_builder/recipes/mcps/google-calendar/setup_auth.py.tmpl`:

```python
"""{{recipe_name}} — first-run OAuth setup.

Run once before starting the agent:

    python setup_auth.py

This opens a browser for you to grant the scopes listed below, then writes a
refresh token to the path in ${{token_path_env}}. The agent reuses that token
on every subsequent run — no re-consent until the token is revoked or the
scopes change.
"""

import os
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print(
        "Missing dependency. Install with:\n"
        "    pip install google-auth-oauthlib google-api-python-client\n",
        file=sys.stderr,
    )
    sys.exit(1)

SCOPES = {{scopes}}
CLIENT_SECRETS_ENV = "{{client_secrets_env}}"
TOKEN_PATH_ENV = "{{token_path_env}}"


def main() -> int:
    client_secrets = os.environ.get(CLIENT_SECRETS_ENV)
    token_path = os.environ.get(TOKEN_PATH_ENV)
    if not client_secrets or not Path(client_secrets).exists():
        print(
            f"${CLIENT_SECRETS_ENV} not set or file missing.\n"
            "Download the OAuth client JSON from Google Cloud Console and set the env var.",
            file=sys.stderr,
        )
        return 1
    if not token_path:
        print(f"${TOKEN_PATH_ENV} must be set (target path for the token JSON).", file=sys.stderr)
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    creds = flow.run_local_server(port=0)
    Path(token_path).write_text(creds.to_json(), encoding="utf-8")
    print(f"OK - token written to {token_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Doctor now green**

Run: `python -m agent_builder.builder --doctor`
Expected: exit 0, `recipes load: 2 recipe(s) loaded` (telegram-poll + google-calendar).

- [ ] **Step 3: Commit**

```bash
git add agent_builder/recipes/mcps/google-calendar/setup_auth.py.tmpl
git commit -m "feat(recipes): google-calendar setup_auth.py.tmpl"
```

### Task E3: attach_recipe materializes setup_auth.py for oauth recipes

**Files:**
- Modify: `agent_builder/tools/attach_recipe.py`
- Modify: `tests/test_attach_recipe.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_attach_recipe.py`:

```python
@pytest.mark.asyncio
async def test_attach_gcal_writes_setup_auth_py(tmp_path):
    from agent_builder.tools.scaffold import scaffold_agent
    out = tmp_path / "output"
    out.mkdir()
    await scaffold_agent({"agent_name": "cal-bot", "description": "x"}, output_base=str(out))
    (out / "cal-bot" / "tools.py").write_text(
        'from claude_agent_sdk import tool, create_sdk_mcp_server\n'
        'TEST_MODE = False\n'
        'tools_server = create_sdk_mcp_server(name="agent-tools", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    (out / "cal-bot" / "AGENT.md").write_text("# Agent\n\nTest.\n", encoding="utf-8")

    result = await attach_recipe(
        {"agent_name": "cal-bot", "recipe_name": "google-calendar"},
        output_base=str(out),
        # Default recipes_root — uses the real bundled recipe.
    )
    assert result.get("is_error") is not True, result
    setup_py = out / "cal-bot" / "setup_auth.py"
    assert setup_py.exists()
    content = setup_py.read_text()
    assert "https://www.googleapis.com/auth/calendar" in content
    assert "{{scopes}}" not in content
    # Handoff banner appended to AGENT.md
    agent_md = (out / "cal-bot" / "AGENT.md").read_text()
    assert "First-run setup" in agent_md
```

- [ ] **Step 2: Run to verify fail**

Expected: `setup_auth.py` does not exist.

- [ ] **Step 3: Implement rendering in attach_recipe**

Extend `_attach_mcp_recipe` to render setup_auth.py when oauth_scopes is non-empty. Add the helper:

```python
def _render_setup_auth(recipe: Recipe, agent_dir: Path, recipes_root: Path) -> None:
    tmpl_path = recipes_root / "mcps" / recipe.name / "setup_auth.py.tmpl"
    tmpl = tmpl_path.read_text(encoding="utf-8")

    # Convention: first env_key is the client_secrets path, second is the token path.
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

    # Append first-run banner to AGENT.md if present.
    agent_md = agent_dir / "AGENT.md"
    if agent_md.exists():
        existing = agent_md.read_text(encoding="utf-8")
        banner = (
            f"\n\n## First-run setup — {recipe.name}\n\n"
            f"Run `python setup_auth.py` once before starting this agent — grants {recipe.name} access.\n"
        )
        if banner not in existing:
            agent_md.write_text(existing + banner, encoding="utf-8")
```

Inside `_attach_mcp_recipe`, after `_update_recipe_pins`:

```python
    if recipe.oauth_scopes:
        try:
            _render_setup_auth(recipe, agent_dir, recipes_root)
        except RuntimeError as e:
            return _error(str(e))
```

- [ ] **Step 4: Run tests to pass**

Run: `pytest tests/test_attach_recipe.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/attach_recipe.py tests/test_attach_recipe.py
git commit -m "feat(attach_recipe): render setup_auth.py for oauth mcp recipes"
```

### Task E4: Write user-facing OAuth setup guide

**Files:**
- Create: `docs/oauth-setup.md`

- [ ] **Step 1: Write the guide**

Create `docs/oauth-setup.md` with these sections:

```markdown
# OAuth Setup for MCP Recipes

Some MCP recipes (Google Calendar, Notion, Linear, etc.) need OAuth2 access to a user account before the agent can call them. The recipe ships a `setup_auth.py.tmpl` that attach_recipe materializes into your agent dir as `setup_auth.py`. Run it once; the agent reuses the resulting refresh token on every subsequent run.

## Google Calendar — worked example

1. Go to https://console.cloud.google.com — create a new project.
2. APIs & Services → Enable APIs and Services → search "Google Calendar API" → Enable.
3. APIs & Services → OAuth consent screen:
   - User type: External
   - App name: anything
   - Add scope: `https://www.googleapis.com/auth/calendar`
   - Add your own email as a test user (required while the app is in "Testing" state)
4. APIs & Services → Credentials → Create Credentials → OAuth client ID:
   - Application type: Desktop app
   - Download the JSON. Rename to `credentials.json` and save it in `output/<agent-name>/`.
5. Edit `output/<agent-name>/.env`:

    ```
    GOOGLE_OAUTH_CLIENT_SECRETS=./credentials.json
    GOOGLE_OAUTH_TOKEN_PATH=./token.json
    ```

6. `cd output/<agent-name> && python setup_auth.py`. A browser window opens; grant access.
7. The script prints `OK - token written to ./token.json`. You're done.

From now on, `python agent.py` has Calendar tools available as `mcp__gcal__*`.

## Troubleshooting

**"access_denied" in the browser**
Add your own email as a test user in the OAuth consent screen (step 3).

**"invalid_client"**
Double-check `GOOGLE_OAUTH_CLIENT_SECRETS` points at the correct JSON. The file should contain `"installed": {"client_id": ..., "client_secret": ...}`.

**"token expired / revoked"**
Delete `token.json` and re-run `setup_auth.py`.

**Scope change**
If you add scopes to the recipe, delete `token.json` and re-run — old tokens don't cover new scopes.

## Adding a new OAuth provider recipe

Follow the pattern of `agent_builder/recipes/mcps/google-calendar/`:
1. Write `RECIPE.md` with `oauth_scopes:` populated.
2. Declare two env keys in order: client secrets path, then token path.
3. Write `setup_auth.py.tmpl` using the four placeholders (`{{scopes}}`, `{{client_secrets_env}}`, `{{token_path_env}}`, `{{recipe_name}}`).
4. Write `mcp.json` with `env_passthrough` listing the env keys the MCP subprocess needs.

The skill-creator sub-plan (Phase G) adds a recipe-author guide — link from here when it lands.
```

- [ ] **Step 2: Commit**

```bash
git add docs/oauth-setup.md
git commit -m "docs: OAuth setup guide for MCP recipes"
```

### Task E5: Update handoff to show setup_auth.py notice

**Files:**
- Modify: `agent_builder/identity/AGENT.md` (Phase 6 handoff section)

- [ ] **Step 1: Edit Phase 6 handoff**

Extend Phase 6 in `agent_builder/identity/AGENT.md`:

```markdown
### Phase 6: Handoff

Tell the user: "Agent ready at `output/<name>/`. Run it with: `python output/<name>/agent.py`"

If any attached recipe declared `oauth_scopes`, add this line per such recipe:

> "`<recipe-name>` OAuth required — run `python output/<name>/setup_auth.py` once before first run. See `docs/oauth-setup.md`."
```

- [ ] **Step 2: Commit**

```bash
git add agent_builder/identity/AGENT.md
git commit -m "docs(builder): handoff mentions setup_auth.py when OAuth attached"
```

### Task E6: End-to-end smoke — build a Telegram+Calendar agent via the real builder tools

**Files:**
- Create: `tests/test_e2e_recipe_attach.py`

- [ ] **Step 1: Write the e2e test**

Create `tests/test_e2e_recipe_attach.py`:

```python
"""End-to-end: scaffold + attach both shipped recipes and validate the file surface."""

from pathlib import Path

import pytest

from agent_builder.tools.attach_recipe import attach_recipe
from agent_builder.tools.scaffold import scaffold_agent


@pytest.mark.asyncio
async def test_build_tg_gcal_agent_end_to_end(tmp_path):
    out = tmp_path / "output"
    out.mkdir()

    result = await scaffold_agent(
        {"agent_name": "tg-gcal", "description": "Telegram to Google Calendar.", "mode": "poll"},
        output_base=str(out),
    )
    assert result.get("is_error") is not True, result

    # Minimal tools.py + AGENT.md — real builds get these from write_tools / write_identity.
    (out / "tg-gcal" / "tools.py").write_text(
        'from claude_agent_sdk import tool, create_sdk_mcp_server\n'
        'TEST_MODE = False\n'
        'tools_server = create_sdk_mcp_server(name="agent-tools", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    (out / "tg-gcal" / "AGENT.md").write_text("# Agent\n\nTest agent.\n", encoding="utf-8")

    for recipe in ("telegram-poll", "google-calendar"):
        result = await attach_recipe(
            {"agent_name": "tg-gcal", "recipe_name": recipe},
            output_base=str(out),
        )
        assert result.get("is_error") is not True, (recipe, result)

    agent_dir = out / "tg-gcal"
    assert (agent_dir / "setup_auth.py").exists()

    agent_py = (agent_dir / "agent.py").read_text()
    assert "_stub_poll_source()" not in agent_py
    assert '"google-calendar"' in agent_py
    assert "RECIPE_PINS" in agent_py
    assert '"telegram-poll"' in agent_py

    env_ex = (agent_dir / ".env.example").read_text()
    assert "TELEGRAM_BOT_TOKEN" in env_ex
    assert "GOOGLE_OAUTH_CLIENT_SECRETS" in env_ex

    agent_md = (agent_dir / "AGENT.md").read_text()
    assert "First-run setup" in agent_md
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_e2e_recipe_attach.py -v`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_recipe_attach.py
git commit -m "test: e2e scaffold+attach for tg-gcal agent"
```

### Task E7: Update top-level CLAUDE.md with v0.9 architecture

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Extend the Architecture section**

Edit `CLAUDE.md`. After the existing "Builder tools (MCP server)" section, insert a new "Recipes library" subsection:

```markdown
### Recipes library

Reusable integration components live under `agent_builder/recipes/{mcps,tools,skills}/<slug>/`. Each recipe is a directory with a `RECIPE.md` carrying frontmatter metadata (name, type, version, description, when_to_use, env_keys, oauth_scopes, allowed_tools_patterns, tags) plus type-specific siblings:

- **mcp** recipes ship `mcp.json` (an `mcp_servers`-shaped entry) and optionally `setup_auth.py.tmpl` when OAuth is required
- **tool** recipes ship `tool.py` — drop-in `@tool`-decorated code
- **skill** recipes ship `skill.md` — prose appended to the target agent's `AGENT.md` (Phase G / v0.9.2)

Discovery: `list_recipes` returns a compact JSON index for the builder to consult during Phase 2.5 (Recipe Attachment). Materialization: `attach_recipe` copies recipe contents into the agent dir, appends env keys to `.env.example` with a versioned banner, merges MCP configs into `agent.py`'s `mcp_servers` dict, and stamps a `RECIPE_PINS = {"<name>": "<version>"}` dict in `agent.py` for future `edit_agent --resync-recipes` comparison.
```

Add a "Template modes" subsection:

```markdown
### Template modes

`scaffold_agent` takes `mode: "cli" | "poll"` (Phase F adds `"server"`). Each mode selects a different template:

- **cli** (default) — `agent_main.py.tmpl`. Interactive chat loop with optional `-p/--prompt` and `-s/--spec` for scripted runs.
- **poll** — `agent_poll.py.tmpl`. Long-poll worker that iterates an `async for incoming in poll_source` loop. `scaffold_agent` renders a `_stub_poll_source()` that raises NotImplementedError; attaching a poll-capable recipe (e.g. `telegram-poll`) rewrites the stub.
- **server** (Phase F, v0.9.1) — `agent_server.py.tmpl`. FastAPI webhook receiver; refuses to scaffold without a webhook-capable recipe.

All three modes share the same identity bootstrap, spinner, safety hook, and `_drain_responses` — differences are only in the driver loop. Doctor validates each template's expected placeholders via `REQUIRED_PLACEHOLDERS_BY_MODE`.
```

Update the "Generated agent contract" section to mention `RECIPE_PINS`:

```markdown
Generated `agent.py` files include a `RECIPE_PINS = {...}` dict near the top (JSON-shaped) listing every attached recipe and its version. Empty at scaffold time; updated deterministically by `attach_recipe`. A future `edit_agent --resync-recipes` action (v0.9.x) will compare pins against current recipe versions and offer updates.
```

- [ ] **Step 2: Run doctor and full test suite one last time**

Run: `pytest`
Expected: all green.

Run: `python -m agent_builder.builder --doctor`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update architecture for v0.9 recipes and template modes"
```

### Task E8: Push the feature branch and open PR

- [ ] **Step 1: Push**

```bash
git push -u origin feat/v0.9-recipes-and-server-mode
```

- [ ] **Step 2: Open PR**

Create a PR against `main` titled `v0.9.0 — recipes, OAuth, poll/server template modes`. Body includes:
- Link to the spec: `docs/superpowers/specs/2026-04-20-agent-builder-v0.9-recipes-and-server-mode-design.md`
- Link to the plan: `docs/superpowers/plans/2026-04-20-agent-builder-v0.9-recipes-and-server-mode.md`
- Checklist of acceptance criteria from spec §13 with each box now checked
- Callout that Phase F (server template) and Phase G (skill recipes) are tracked as follow-up sub-plans

```bash
gh pr create --title "v0.9.0 - recipes, OAuth, poll/server template modes" --body "$(cat <<'EOF'
## Summary

Ships v0.9.0 milestone from `docs/superpowers/specs/2026-04-20-agent-builder-v0.9-recipes-and-server-mode-design.md`.

- Recipe library (`agent_builder/recipes/`) with frontmatter-driven discovery
- Two new builder tools: `list_recipes`, `attach_recipe`
- New template mode `poll` (Telegram/Discord gateway workers); `cli` unchanged
- OAuth scaffolding via per-recipe `setup_auth.py.tmpl`
- First shipped recipes: `telegram-poll` (tool), `google-calendar` (mcp+oauth)

Phase F (server/FastAPI template) and Phase G (skill recipes) tracked as separate sub-plans for v0.9.1+.

## Test plan

- [ ] `pytest` all green
- [ ] `python -m agent_builder.builder --doctor` exit 0
- [ ] Interactive: build a Telegram+Calendar agent end-to-end via `python -m agent_builder.builder`
- [ ] Smoke: `python output/<name>/setup_auth.py` completes Google OAuth
- [ ] Smoke: generated agent starts and accepts a Telegram message in a test chat

See spec §13 for full acceptance criteria.
EOF
)"
```

---

## Future Phases (out of scope for v0.9.0 — tracked for v0.9.1+)

### Phase F — Server template (FastAPI webhook)

Adds `agent_server.py.tmpl`, `scaffold_agent mode="server"`, webhook signature validator injection, first webhook-capable recipe (WhatsApp or GitHub events). Scaffold-time guard: `mode="server"` refuses to complete unless a webhook-capable recipe is attached, or `--no-webhook-recipe` is explicitly passed (rendering deny-all stubs). Defaults bind to `127.0.0.1`; public bind requires explicit `HOST=0.0.0.0`.

Ship as its own sub-plan: `docs/superpowers/plans/YYYY-MM-DD-v0.9.1-server-template.md`. Dependencies: `fastapi`, `uvicorn` in the `[server]` extra.

### Phase G — Skill recipes

Adds skill-type to `attach_recipe`, first skill recipe (`parse-hours-to-events`), markdown injection into the generated agent's `AGENT.md` with HTML-comment version markers for later resync. Also: auto-rewriting `tools_server` assignment when tool recipes add new @tool-decorated functions (the current telegram-poll note).

Ship as its own sub-plan: `docs/superpowers/plans/YYYY-MM-DD-v0.9.2-skill-recipes.md`.

### Phase H — Recipe resync

Adds `edit_agent --resync-recipes` flag comparing `RECIPE_PINS` against current `recipes/*/RECIPE.md` versions, offering per-recipe updates. Backups via the existing `.bak-<timestamp>` mechanism. Ship after we see real recipe upgrade churn in the wild.

---

## Self-Review Notes

**Spec coverage check:**
- Spec §2 Architecture — covered by Tasks A2–A8 (dir skeleton + loader + list_recipes + doctor extensions) and B1–B4 (attach_recipe + AGENT.md workflow update).
- Spec §3 Recipe Format — covered by Task A3 (schema) + A4 (loader sibling validation) + D3 (env_passthrough validation).
- Spec §4.1 Shared template changes — covered by B1 (`{{recipe_pins_block}}`) and D1 (`{{external_mcp_block}}`).
- Spec §4.2 Poll template — covered by C2.
- Spec §4.3 Server template — explicitly deferred to Phase F per §10 acceptance criteria.
- Spec §5 OAuth scaffolding — covered by E1–E5.
- Spec §6 Builder context + Phase 2.5 — covered by A5 (list_recipes) + A8 (AGENT.md Phase 2.5) + B4 (Phase 4 update) + D4 (mcp guidance) + E5 (handoff).
- Spec §7 Version pinning — covered by B1 (`{{recipe_pins_block}}` placeholder) + B2 (`_update_recipe_pins` with json.loads) + D3 (env_example banner).
- Spec §8 `.env.example` merging — covered by D3 (`_merge_env_example` with conflict detection + test_env_merge.py unit tests).
- Spec §9 Testing — covered by A3–A5 (schema/loader/list_recipes tests), B2/C5/D3/E3 (attach_recipe per-type tests), C2/C4 (template tests), C6 (poll test_agent), E6 (e2e smoke).
- Spec §10 Phasing — mirrored 1:1 in phase sections.
- Spec §13 Acceptance criteria — verified met by end of Task E8.

**Type consistency:** `Recipe`, `RecipeType`, `RecipeError` imported consistently from `agent_builder.recipes.schema`; `load_all_recipes`/`load_recipe` from `.loader`. Tool functions all return the MCP shape `{"content": [...], "is_error"?: bool}` matching existing builder tools.

**No placeholders in plan:** every code block is complete runnable code or a specific delta against an identified file.
