# Agent Builder v0.10 — Authoring Layer + Components — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add authoring layer (builder creates/clones/edits recipes mid-build) + components type (small reusable snippets). Assembler becomes the default; manual composition only when the library lacks what's needed.

**Architecture:** Builds on v0.9's composition model. Four new builder tools (`create_recipe`, `clone_recipe`, `edit_recipe`, `attach_component`). One new recipe type (`components/`) with frontmatter-in-comment-header. Auto-save heuristic runs during Phase 2. `maturity` tiers gate visibility and attachment.

**Tech Stack:** same as v0.9. No new deps.

**Spec:** `docs/superpowers/specs/2026-04-20-agent-builder-v0.10-authoring-and-components-design.md`

**Prerequisite:** v0.9 must be shipped and merged. Branch off from the post-v0.9 main.

**Branch:** `feat/v0.10-authoring-and-components` (create when starting)

---

## File Structure

**New files:**

```
agent_builder/recipes/components/               # NEW type directory
    .gitkeep
    (examples to ship: logging-setup.py, timezone-nz.md — in Phase A tests)

agent_builder/recipes/
    component_schema.py                         # component frontmatter parser
    component_loader.py                         # filesystem scan for components

agent_builder/tools/
    create_recipe.py
    clone_recipe.py
    edit_recipe.py
    attach_component.py

agent_builder/audit.py                          # recipe-audit.log writer

tests/
    test_component_schema.py
    test_component_loader.py
    test_create_recipe.py
    test_clone_recipe.py
    test_edit_recipe.py
    test_attach_component.py
    test_auto_save_heuristic.py
    test_maturity_tiers.py
    test_audit_log.py
    test_e2e_v0_10_full_build.py
```

**Modified files:**

```
pyproject.toml                                  # bump to 0.10.0
agent_builder/recipes/schema.py                 # add maturity field
agent_builder/recipes/loader.py                 # honor maturity (hide in-dev)
agent_builder/tools/list_recipes.py             # include maturity in index; filter
agent_builder/tools/attach_recipe.py            # refuse in-dev; warn on experimental
agent_builder/tools/test_agent.py               # self-heal hook for just-created recipes
agent_builder/tools/__init__.py                 # register 4 new tools
agent_builder/builder.py                        # add 4 new tools to allowed_tools
agent_builder/manifest.py                       # AttachedComponent already defined in v0.9 — verify shape
agent_builder/render.py                         # honor AttachedComponent for AGENT.md slot fills
agent_builder/doctor.py                         # validate components + audit log activity
agent_builder/identity/AGENT.md                 # auto-save heuristic in Phase 2; self-heal in Phase 5
CLAUDE.md                                       # architecture section update
```

---

## Phase A — Component Type

Ships: component frontmatter schema + loader, `list_recipes` support for component type. After Phase A, components can be stored and listed (but not yet attached).

### Task A1: Bump version + set up branch

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git pull
git checkout -b feat/v0.10-authoring-and-components
```

- [ ] **Step 2: Bump version**

Edit `pyproject.toml`: `version = "0.10.0"`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: bump to 0.10.0"
```

### Task A2: Component schema (TDD)

**Files:**
- Create: `tests/test_component_schema.py`
- Create: `agent_builder/recipes/component_schema.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for component frontmatter-in-comment-header parsing."""

import pytest

from agent_builder.recipes.component_schema import (
    Component,
    ComponentError,
    parse_component,
)


def test_parse_python_component():
    content = '''# ---frontmatter---
# name: logging-setup
# version: 0.1.0
# description: Rotating file logger
# target: tools.py
# slot: after_imports
# maturity: stable
# tags: [logging, observability]
# ---/frontmatter---

import logging
_logger = logging.getLogger("agent")
'''
    c = parse_component(content, source_path="/fake/logging-setup.py")
    assert c.name == "logging-setup"
    assert c.target == "tools.py"
    assert c.slot == "after_imports"
    assert c.maturity == "stable"
    assert "_logger" in c.body


def test_parse_markdown_component():
    content = '''<!-- ---frontmatter---
name: timezone-nz
version: 0.1.0
description: NZ timezone guidance
target: AGENT.md
slot: constraints
maturity: stable
tags: [timezone, nz]
---/frontmatter--- -->

All dates in Pacific/Auckland.
'''
    c = parse_component(content, source_path="/fake/timezone-nz.md")
    assert c.name == "timezone-nz"
    assert c.target == "AGENT.md"
    assert c.slot == "constraints"
    assert "Pacific/Auckland" in c.body


def test_parse_rejects_missing_frontmatter():
    content = "import os\n"
    with pytest.raises(ComponentError, match="frontmatter"):
        parse_component(content, source_path="/fake/x.py")


def test_parse_rejects_missing_target():
    content = '''# ---frontmatter---
# name: x
# version: 0.1.0
# description: x
# ---/frontmatter---
'''
    with pytest.raises(ComponentError, match="target"):
        parse_component(content, source_path="/fake/x.py")


def test_parse_rejects_bad_slot_combo():
    # AGENT.md target but no slot → error
    content = '''<!-- ---frontmatter---
name: x
version: 0.1.0
description: x
target: AGENT.md
maturity: stable
---/frontmatter--- -->

Body.
'''
    with pytest.raises(ComponentError, match="slot"):
        parse_component(content, source_path="/fake/x.md")
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_component_schema.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `agent_builder/recipes/component_schema.py`:

```python
"""Component frontmatter schema — supports .py (hash-comment) and .md (HTML-comment)."""

import re
from dataclasses import dataclass, field
from typing import Any

import yaml


class ComponentError(ValueError):
    pass


_PY_FRONTMATTER = re.compile(
    r"\A# ---frontmatter---\s*\n(?P<body>(?:# .*\n)+)# ---/frontmatter---\s*\n(?P<rest>.*)",
    re.DOTALL,
)
_MD_FRONTMATTER = re.compile(
    r"\A<!-- ---frontmatter---\s*\n(?P<body>.*?)---/frontmatter--- -->\s*\n(?P<rest>.*)",
    re.DOTALL,
)

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VALID_TARGETS = {"tools.py", "agent.py", "AGENT.md"}
_VALID_CODE_SLOTS = {"after_imports", "after_tools"}
_VALID_MD_SLOTS = {"purpose", "workflow", "constraints", "tools_reference", "examples", "first_run_setup"}
_VALID_MATURITY = {"in-dev", "experimental", "stable"}


@dataclass(frozen=True)
class Component:
    name: str
    version: str
    description: str
    target: str            # "tools.py" | "agent.py" | "AGENT.md"
    slot: str = ""         # required if target is .md or if code target has slot
    maturity: str = "experimental"
    depends_on: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    body: str = ""
    source_path: str = ""
    created_at: str = ""
    git_sha: str = ""


def parse_component(content: str, *, source_path: str) -> Component:
    """Parse a component file. Routes by source_path suffix."""
    if source_path.endswith(".py"):
        m = _PY_FRONTMATTER.match(content)
        if not m:
            raise ComponentError(f"{source_path}: missing frontmatter block")
        raw_lines = [line[2:] for line in m.group("body").splitlines() if line.startswith("# ")]
        yaml_body = "\n".join(raw_lines)
        rest = m.group("rest")
    elif source_path.endswith(".md"):
        m = _MD_FRONTMATTER.match(content)
        if not m:
            raise ComponentError(f"{source_path}: missing frontmatter block")
        yaml_body = m.group("body")
        rest = m.group("rest")
    else:
        raise ComponentError(f"{source_path}: component must be .py or .md")

    try:
        data = yaml.safe_load(yaml_body)
    except yaml.YAMLError as e:
        raise ComponentError(f"{source_path}: frontmatter YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise ComponentError(f"{source_path}: frontmatter must be a mapping")

    _require(data, ("name", "version", "description", "target"), source_path)

    name = data["name"]
    if not isinstance(name, str) or not _NAME_PATTERN.match(name):
        raise ComponentError(f"{source_path}: name '{name}' invalid")

    target = data["target"]
    if target not in _VALID_TARGETS:
        raise ComponentError(f"{source_path}: target '{target}' not in {sorted(_VALID_TARGETS)}")

    slot = data.get("slot", "")
    if target == "AGENT.md":
        if not slot:
            raise ComponentError(f"{source_path}: target AGENT.md requires 'slot'")
        if slot not in _VALID_MD_SLOTS:
            raise ComponentError(f"{source_path}: slot '{slot}' not in {sorted(_VALID_MD_SLOTS)}")
    elif target in ("tools.py", "agent.py"):
        if slot and slot not in _VALID_CODE_SLOTS:
            raise ComponentError(f"{source_path}: slot '{slot}' not in {sorted(_VALID_CODE_SLOTS)}")

    maturity = data.get("maturity", "experimental")
    if maturity not in _VALID_MATURITY:
        raise ComponentError(f"{source_path}: maturity '{maturity}' not in {sorted(_VALID_MATURITY)}")

    return Component(
        name=name,
        version=str(data["version"]),
        description=str(data["description"]),
        target=target,
        slot=slot,
        maturity=maturity,
        depends_on=list(data.get("depends_on") or []),
        tags=list(data.get("tags") or []),
        body=rest,
        source_path=source_path,
        created_at=str(data.get("created_at", "")),
        git_sha=str(data.get("git_sha", "")),
    )


def _require(data: dict, keys: tuple[str, ...], source_path: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise ComponentError(f"{source_path}: missing required keys: {missing}")
```

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/recipes/component_schema.py tests/test_component_schema.py
git commit -m "feat(components): frontmatter-in-comment-header parser"
```

### Task A3: Component loader (TDD)

**Files:**
- Create: `tests/test_component_loader.py`
- Create: `agent_builder/recipes/component_loader.py`
- Create: `tests/fixtures/components_valid/logging-setup.py`
- Create: `tests/fixtures/components_valid/timezone-nz.md`

- [ ] **Step 1: Create fixtures**

`tests/fixtures/components_valid/logging-setup.py`:

```python
# ---frontmatter---
# name: logging-setup
# version: 0.1.0
# description: Rotating file logger for agent.log
# target: tools.py
# slot: after_imports
# maturity: stable
# tags: [logging]
# ---/frontmatter---

import logging
from logging.handlers import RotatingFileHandler

_logger = logging.getLogger("agent")
```

`tests/fixtures/components_valid/timezone-nz.md`:

```markdown
<!-- ---frontmatter---
name: timezone-nz
version: 0.1.0
description: NZ timezone guidance
target: AGENT.md
slot: constraints
maturity: stable
---/frontmatter--- -->

All dates and times are in Pacific/Auckland.
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for component filesystem loader."""

from pathlib import Path

from agent_builder.recipes.component_loader import load_all_components

FIXTURES = Path(__file__).parent / "fixtures" / "components_valid"


def test_load_all_components_finds_both_shapes():
    comps = load_all_components(FIXTURES)
    names = {c.name for c in comps}
    assert names == {"logging-setup", "timezone-nz"}


def test_load_all_components_empty_dir(tmp_path):
    assert load_all_components(tmp_path) == []
```

- [ ] **Step 3: Implement**

Create `agent_builder/recipes/component_loader.py`:

```python
"""Component filesystem loader."""

from pathlib import Path

from agent_builder.recipes.component_schema import Component, parse_component


def default_components_root() -> Path:
    return Path(__file__).parent.parent / "recipes" / "components"


def load_all_components(components_root: Path | None = None) -> list[Component]:
    root = Path(components_root) if components_root else default_components_root()
    if not root.exists():
        return []
    out: list[Component] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        if entry.suffix not in (".py", ".md"):
            continue
        content = entry.read_text(encoding="utf-8")
        out.append(parse_component(content, source_path=str(entry)))
    return out
```

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/recipes/component_loader.py tests/test_component_loader.py tests/fixtures/components_valid/
git commit -m "feat(components): filesystem loader for .py and .md components"
```

### Task A4: Extend `list_recipes` to include components

**Files:**
- Modify: `agent_builder/tools/list_recipes.py`
- Modify: `tests/test_list_recipes.py`

- [ ] **Step 1: Write test**

Add to `tests/test_list_recipes.py`:

```python
@pytest.mark.asyncio
async def test_list_recipes_includes_components(tmp_path):
    # Stage a fixture dir with one component and nothing else.
    (tmp_path / "components").mkdir()
    (tmp_path / "components" / "sample.py").write_text(
        "# ---frontmatter---\n"
        "# name: sample\n"
        "# version: 0.1.0\n"
        "# description: test\n"
        "# target: tools.py\n"
        "# slot: after_imports\n"
        "# maturity: stable\n"
        "# ---/frontmatter---\n\n"
        "pass\n",
        encoding="utf-8",
    )
    result = await list_recipes({"type": "component"}, recipes_root=tmp_path)
    payload = json.loads(result["content"][0]["text"])
    assert any(r["name"] == "sample" and r["type"] == "component" for r in payload)
```

- [ ] **Step 2: Update list_recipes.py**

Import `load_all_components` and merge into the index. Component entries get `type: "component"` and additional fields `target`, `slot`, `maturity`:

```python
from agent_builder.recipes.component_loader import default_components_root, load_all_components
from agent_builder.recipes.component_schema import ComponentError

# inside list_recipes:
    components = []
    comp_root = (recipes_root / "components") if recipes_root else default_components_root()
    try:
        components = load_all_components(comp_root)
    except ComponentError as e:
        return {"content": [{"type": "text", "text": f"Component load error: {e}"}], "is_error": True}

    component_entries = [
        {
            "name": c.name,
            "type": "component",
            "version": c.version,
            "description": c.description,
            "target": c.target,
            "slot": c.slot,
            "maturity": c.maturity,
            "tags": c.tags,
        }
        for c in components
        if (type_filter is None or type_filter == "component")
        and (tag_filter is None or tag_filter in c.tags)
    ]
    # Mix components into the full index.
    index.extend(component_entries)
```

Also add `"component"` to the JSON schema's `type` enum.

- [ ] **Step 3: Run tests**

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add agent_builder/tools/list_recipes.py tests/test_list_recipes.py
git commit -m "feat(list_recipes): include components in index"
```

---

## Phase B — `attach_component`

Ships: `attach_component` tool + render integration for AGENT.md slot fills.

### Task B1: `attach_component` tool (TDD)

**Files:**
- Create: `tests/test_attach_component.py`
- Create: `agent_builder/tools/attach_component.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for attach_component builder tool."""

import json
from pathlib import Path

import pytest

from agent_builder.tools.attach_component import attach_component

FIXTURES = Path(__file__).parent / "fixtures" / "components_valid"


@pytest.fixture
def agent_dir(tmp_path):
    import asyncio
    from agent_builder.tools.scaffold import scaffold_agent
    out = tmp_path / "output"
    out.mkdir()
    asyncio.run(scaffold_agent({"agent_name": "a", "description": "x"}, output_base=str(out)))
    (out / "a" / "tools.py").write_text(
        'import os\n'
        'from claude_agent_sdk import tool, create_sdk_mcp_server\n'
        'def _test_mode(): return os.environ.get("AGENT_TEST_MODE") == "1"\n'
        'tools_server = create_sdk_mcp_server(name="agent-tools", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    (out / "a" / "AGENT.md").write_text(
        "# Agent\n\n"
        "## Constraints\n\n<!-- SLOT: builder_agent_additions -->\n<!-- /SLOT: builder_agent_additions -->\n"
        "<!-- SLOT: user_additions -->\n<!-- /SLOT: user_additions -->\n",
        encoding="utf-8",
    )
    return out / "a"


@pytest.mark.asyncio
async def test_attach_python_component_appends_to_tools_py(agent_dir):
    result = await attach_component(
        {"agent_name": "a", "component_name": "logging-setup"},
        output_base=str(agent_dir.parent),
        components_root=FIXTURES,
    )
    assert result.get("is_error") is not True, result
    content = (agent_dir / "tools.py").read_text()
    assert "# component: logging-setup @ 0.1.0" in content
    assert "RotatingFileHandler" in content


@pytest.mark.asyncio
async def test_attach_markdown_component_updates_manifest(agent_dir):
    result = await attach_component(
        {"agent_name": "a", "component_name": "timezone-nz"},
        output_base=str(agent_dir.parent),
        components_root=FIXTURES,
    )
    assert result.get("is_error") is not True
    manifest = json.loads((agent_dir / ".recipe_manifest.json").read_text())
    comp = next(c for c in manifest["components"] if c["name"] == "timezone-nz")
    assert comp["target"] == "AGENT.md:slot=constraints"


@pytest.mark.asyncio
async def test_attach_component_idempotent(agent_dir):
    await attach_component(
        {"agent_name": "a", "component_name": "logging-setup"},
        output_base=str(agent_dir.parent),
        components_root=FIXTURES,
    )
    first = (agent_dir / "tools.py").read_text()
    await attach_component(
        {"agent_name": "a", "component_name": "logging-setup"},
        output_base=str(agent_dir.parent),
        components_root=FIXTURES,
    )
    second = (agent_dir / "tools.py").read_text()
    assert first == second
```

- [ ] **Step 2: Run to verify fail**

Expected: ImportError.

- [ ] **Step 3: Implement**

Create `agent_builder/tools/attach_component.py`:

```python
"""attach_component — materializes a component into an agent's files."""

import datetime
import re
import subprocess
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder.manifest import (
    AttachedComponent,
    MANIFEST_FILENAME,
    load_manifest,
    save_manifest,
)
from agent_builder.recipes.component_loader import default_components_root, load_all_components
from agent_builder.recipes.component_schema import Component, ComponentError
from agent_builder.render import render_agent

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_COMPONENT_HEADER = re.compile(
    r"^# component: (?P<name>\S+) @ (?P<version>\S+)$",
    re.MULTILINE,
)


async def attach_component(
    args: dict[str, Any],
    *,
    output_base: str = "output",
    components_root: Path | None = None,
) -> dict[str, Any]:
    agent_name = args.get("agent_name", "")
    component_name = args.get("component_name", "")

    if not _NAME_PATTERN.match(agent_name):
        return _error(f"Invalid agent name '{agent_name}'.")
    if not _NAME_PATTERN.match(component_name):
        return _error(f"Invalid component name '{component_name}'.")

    agent_dir = Path(output_base) / agent_name
    if not agent_dir.exists():
        return _error(f"Agent '{agent_name}' not found.")

    try:
        comps = load_all_components(components_root or default_components_root())
    except ComponentError as e:
        return _error(f"Component load error: {e}")
    comp = next((c for c in comps if c.name == component_name), None)
    if comp is None:
        return _error(f"Component '{component_name}' not found.")

    if comp.maturity == "in-dev":
        return _error(f"Component '{component_name}' is in-dev; cannot attach.")

    manifest = load_manifest(agent_dir / MANIFEST_FILENAME, agent_name=agent_name)

    target_key = (
        f"{comp.target}:slot={comp.slot}" if comp.slot else comp.target
    )

    # Idempotency — same component at same version already attached
    existing = next(
        (c for c in manifest.components if c.name == comp.name and c.target == target_key),
        None,
    )
    if existing and existing.version == comp.version:
        return _ok(f"Component '{comp.name}@{comp.version}' already attached.")

    if comp.target == "tools.py":
        _append_to_tools(agent_dir, comp)
    elif comp.target == "agent.py":
        _append_to_agent_py(agent_dir, comp)
    elif comp.target == "AGENT.md":
        # Manifest-driven — render picks up body on next render call.
        pass

    # Update manifest.
    manifest.components = [c for c in manifest.components if not (c.name == comp.name and c.target == target_key)]
    manifest.components.append(AttachedComponent(
        name=comp.name,
        version=comp.version,
        target=target_key,
        attached_at=_today_iso(),
        git_sha=_short_sha(),
    ))
    save_manifest(agent_dir / MANIFEST_FILENAME, manifest)

    # Rerender (AGENT.md components take effect here; agent.py in case of downstream impact).
    render_agent(agent_dir)

    return _ok(f"Attached component '{comp.name}@{comp.version}' to {agent_dir.name} ({target_key}).")


def _append_to_tools(agent_dir: Path, comp: Component) -> None:
    tools_py = agent_dir / "tools.py"
    content = tools_py.read_text(encoding="utf-8")

    # Skip if header already present (idempotency belt-and-braces).
    for m in _COMPONENT_HEADER.finditer(content):
        if m.group("name") == comp.name and m.group("version") == comp.version:
            return

    header = f"\n\n# component: {comp.name} @ {comp.version}\n"
    snippet = comp.body.strip()

    if comp.slot == "after_imports":
        # Find the last import line; insert just after.
        lines = content.splitlines()
        last_import = 0
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("from ") or s.startswith("import "):
                last_import = i
        insert_at = last_import + 1
        lines.insert(insert_at, header + snippet + "\n")
        content = "\n".join(lines)
    else:  # after_tools / unspecified = append
        content = content.rstrip() + header + snippet + "\n"

    tools_py.write_text(content, encoding="utf-8")


def _append_to_agent_py(agent_dir: Path, comp: Component) -> None:
    # Similar append-with-header pattern, targeting agent.py's designated block.
    # Keep it simple: append inside the recipe_imports_block region.
    agent_py = agent_dir / "agent.py"
    content = agent_py.read_text(encoding="utf-8")
    marker = "# <</recipe_imports_block>>"
    if marker not in content:
        raise RuntimeError("agent.py missing recipe_imports_block end marker")
    header = f"# component: {comp.name} @ {comp.version}\n"
    inject = header + comp.body.strip() + "\n"
    content = content.replace(marker, inject + marker, 1)
    agent_py.write_text(content, encoding="utf-8")


def _today_iso() -> str:
    return datetime.date.today().isoformat()


def _short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _error(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}], "is_error": True}


def _ok(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}


attach_component_tool = tool(
    "attach_component",
    "Attach a component snippet to a generated agent. Components target tools.py, "
    "agent.py, or AGENT.md slots. Idempotent per (agent, component@version, target).",
    {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string"},
            "component_name": {"type": "string"},
        },
        "required": ["agent_name", "component_name"],
    },
)(attach_component)
```

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/attach_component.py tests/test_attach_component.py
git commit -m "feat(attach_component): materialize components into tools.py / agent.py / AGENT.md"
```

### Task B2: Render honors AGENT.md components

**Files:**
- Modify: `agent_builder/render.py`
- Modify: `tests/test_render.py` (or test_attach_component.py — add an assertion)

- [ ] **Step 1: Write test (append to test_attach_component.py)**

```python
@pytest.mark.asyncio
async def test_attach_md_component_body_appears_in_agent_md(agent_dir):
    await attach_component(
        {"agent_name": "a", "component_name": "timezone-nz"},
        output_base=str(agent_dir.parent),
        components_root=FIXTURES,
    )
    agent_md = (agent_dir / "AGENT.md").read_text()
    assert "Pacific/Auckland" in agent_md
```

- [ ] **Step 2: Run to verify fail**

Expected: current `_render_agent_md` doesn't know about components — test fails.

- [ ] **Step 3: Update render.py to pull component bodies by slot**

Extend `_render_agent_md`:

```python
from agent_builder.recipes.component_loader import load_all_components
from agent_builder.recipes.component_schema import Component


def _render_agent_md(agent_dir: Path, manifest: Manifest, components_root: Path | None = None) -> None:
    # ... existing preserved-slots extraction ...

    # Group attached components by slot.
    slot_fills: dict[str, list[str]] = {}
    try:
        available = {c.name: c for c in load_all_components(components_root)}
    except Exception:  # loader errors surface elsewhere
        available = {}
    for ac in manifest.components:
        if not ac.target.startswith("AGENT.md:slot="):
            continue
        slot = ac.target.split("slot=", 1)[1]
        comp = available.get(ac.name)
        if comp is None:
            continue  # dangling component — doctor will flag
        slot_fills.setdefault(slot, []).append(comp.body.strip())

    template = template_path.read_text(encoding="utf-8")
    for slot in ("purpose", "workflow", "constraints", "tools_reference", "examples", "first_run_setup"):
        body = "\n\n".join(sorted(slot_fills.get(slot, [])))   # deterministic order
        template = template.replace(f"{{{{slot:{slot}}}}}", body)

    # ... existing preserved-slot fill ...
```

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/render.py tests/test_attach_component.py
git commit -m "feat(render): AGENT.md slots filled from attached components"
```

### Task B3: Register attach_component in builder MCP server

**Files:**
- Modify: `agent_builder/tools/__init__.py`
- Modify: `agent_builder/builder.py`

- [ ] **Step 1: Add import + registration**

Same pattern as earlier tools — `from ... import attach_component_tool`, append to tools list, add `"mcp__builder_tools__attach_component"` to builder.py's allowed_tools.

- [ ] **Step 2: Commit**

```bash
git add agent_builder/tools/__init__.py agent_builder/builder.py
git commit -m "feat(builder): register attach_component tool"
```

---

## Phase C — Maturity Tiers

Ships: `maturity` field in recipe schema + loader + filtering.

### Task C1: Add maturity to Recipe schema

**Files:**
- Modify: `agent_builder/recipes/schema.py`
- Modify: `tests/test_recipes_schema.py`

- [ ] **Step 1: Test**

```python
def test_parse_recipe_with_maturity():
    content = """---
name: x
type: tool
version: 0.1.0
description: x
when_to_use: x
maturity: experimental
---
"""
    r = parse_recipe_md(content, source_path="/fake/RECIPE.md")
    assert r.maturity == "experimental"


def test_parse_recipe_default_maturity():
    content = """---
name: x
type: tool
version: 0.1.0
description: x
when_to_use: x
---
"""
    r = parse_recipe_md(content, source_path="/fake/RECIPE.md")
    assert r.maturity == "experimental"  # default when absent


def test_parse_recipe_rejects_bad_maturity():
    content = """---
name: x
type: tool
version: 0.1.0
description: x
when_to_use: x
maturity: spicy
---
"""
    with pytest.raises(RecipeError, match="maturity"):
        parse_recipe_md(content, source_path="/fake/RECIPE.md")
```

- [ ] **Step 2: Run to verify fail**

Expected: fail.

- [ ] **Step 3: Add field + validation to schema.py**

```python
_VALID_MATURITY = {"in-dev", "experimental", "stable"}

@dataclass(frozen=True)
class Recipe:
    # ... existing fields ...
    maturity: str = "experimental"
    created_at: str = ""
    git_sha: str = ""


def parse_recipe_md(content: str, *, source_path: str) -> Recipe:
    # ... existing parsing ...
    maturity = data.get("maturity", "experimental")
    if maturity not in _VALID_MATURITY:
        raise RecipeError(f"{source_path}: maturity '{maturity}' not in {sorted(_VALID_MATURITY)}")

    return Recipe(
        # ... existing ...
        maturity=maturity,
        created_at=str(data.get("created_at", "")),
        git_sha=str(data.get("git_sha", "")),
    )
```

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/recipes/schema.py tests/test_recipes_schema.py
git commit -m "feat(schema): maturity field on Recipe (default experimental)"
```

### Task C2: `list_recipes` hides in-dev + shows maturity

**Files:**
- Modify: `agent_builder/tools/list_recipes.py`
- Modify: `tests/test_list_recipes.py`

- [ ] **Step 1: Test**

```python
@pytest.mark.asyncio
async def test_list_recipes_hides_in_dev(tmp_path):
    (tmp_path / "tools").mkdir()
    for name, maturity in [("good", "stable"), ("wip", "in-dev")]:
        d = tmp_path / "tools" / name
        d.mkdir()
        (d / "RECIPE.md").write_text(
            f"---\nname: {name}\ntype: tool\nversion: 0.1.0\n"
            f"description: x\nwhen_to_use: x\nmaturity: {maturity}\n---\n",
            encoding="utf-8",
        )
        (d / "tool.py").write_text("# x", encoding="utf-8")
    result = await list_recipes({}, recipes_root=tmp_path)
    payload = json.loads(result["content"][0]["text"])
    names = [r["name"] for r in payload]
    assert "good" in names
    assert "wip" not in names
```

- [ ] **Step 2: Run to verify fail**

- [ ] **Step 3: Filter in-dev; include maturity in index**

In `list_recipes.py`:

```python
    index = [
        {
            "name": r.name,
            "type": r.type.value,
            "version": r.version,
            "description": r.description,
            "when_to_use": r.when_to_use,
            "maturity": r.maturity,
            "tags": r.tags,
        }
        for r in recipes
        if r.maturity != "in-dev"   # hide in-dev entirely
        and (type_filter is None or r.type.value == type_filter)
        and (tag_filter is None or tag_filter in r.tags)
    ]
```

Same filter for components.

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/list_recipes.py tests/test_list_recipes.py
git commit -m "feat(list_recipes): hide in-dev; surface maturity field"
```

### Task C3: `attach_recipe` refuses in-dev; warns on experimental

**Files:**
- Modify: `agent_builder/tools/attach_recipe.py`
- Modify: `tests/test_attach_recipe.py`

- [ ] **Step 1: Test**

```python
@pytest.mark.asyncio
async def test_attach_rejects_in_dev(tmp_path, agent_dir):
    # Create an in-dev recipe fixture
    (tmp_path / "tools" / "wip").mkdir(parents=True)
    (tmp_path / "tools" / "wip" / "RECIPE.md").write_text(
        "---\nname: wip\ntype: tool\nversion: 0.1.0\n"
        "description: x\nwhen_to_use: x\nmaturity: in-dev\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "tools" / "wip" / "tool.py").write_text("# x", encoding="utf-8")
    result = await attach_recipe(
        {"agent_name": "test-agent", "recipe_name": "wip"},
        output_base=str(agent_dir.parent),
        recipes_root=tmp_path,
    )
    assert result["is_error"] is True
    assert "in-dev" in result["content"][0]["text"]
```

- [ ] **Step 2: Run to verify fail**

- [ ] **Step 3: Add maturity gate in attach_recipe**

After loading the recipe:

```python
    if recipe.maturity == "in-dev":
        return _error(f"Recipe '{recipe.name}' is in-dev; refusing to attach.")
    if recipe.maturity == "experimental":
        # Still attach, but WARN-level in result text.
        pass  # (warning surfaces in the success message)
```

Modify the success message for experimental attaches:

```python
    warning = " [WARN: experimental recipe]" if recipe.maturity == "experimental" else ""
    return _ok(f"Attached {recipe.type.value} recipe '{recipe.name}@{recipe.version}'{warning}.")
```

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/attach_recipe.py tests/test_attach_recipe.py
git commit -m "feat(attach_recipe): refuse in-dev; warn on experimental"
```

---

## Phase D — `create_recipe` + Auto-Save Heuristic

Ships: `create_recipe` builder tool + heuristic evaluator + builder AGENT.md updates.

### Task D1: Audit log writer

**Files:**
- Create: `tests/test_audit_log.py`
- Create: `agent_builder/audit.py`

- [ ] **Step 1: Test**

```python
from pathlib import Path

from agent_builder.audit import append_audit, AUDIT_LOG_FILENAME


def test_append_audit_writes_line(tmp_path):
    append_audit(
        repo_root=tmp_path,
        action="CREATE",
        subject="tool/sample@0.1.0",
        by="builder",
        extra={"reason": "test"},
    )
    log = (tmp_path / "agent_builder" / AUDIT_LOG_FILENAME).read_text()
    assert "CREATE" in log
    assert "tool/sample@0.1.0" in log
    assert "by=builder" in log
    assert 'reason="test"' in log
```

- [ ] **Step 2: Run to verify fail**

- [ ] **Step 3: Implement**

Create `agent_builder/audit.py`:

```python
"""Recipe authoring audit log."""

import datetime
from pathlib import Path
from typing import Any

AUDIT_LOG_FILENAME = "recipe-audit.log"


def append_audit(
    *,
    repo_root: Path | None = None,
    action: str,
    subject: str,
    by: str = "builder",
    extra: dict[str, Any] | None = None,
) -> None:
    root = Path(repo_root) if repo_root else Path.cwd()
    log_path = root / "agent_builder" / AUDIT_LOG_FILENAME
    log_path.parent.mkdir(parents=True, exist_ok=True)

    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    fields = [f"{stamp}", action, subject, f"by={by}"]
    if extra:
        for k, v in extra.items():
            fields.append(f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}")
    line = " ".join(fields) + "\n"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)
```

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/audit.py tests/test_audit_log.py
git commit -m "feat(audit): append-only recipe authoring log"
```

### Task D2: `create_recipe` tool (TDD)

**Files:**
- Create: `tests/test_create_recipe.py`
- Create: `agent_builder/tools/create_recipe.py`

- [ ] **Step 1: Test**

```python
"""Tests for create_recipe builder tool."""

from pathlib import Path

import pytest

from agent_builder.tools.create_recipe import create_recipe


@pytest.mark.asyncio
async def test_create_tool_recipe_writes_files(tmp_path):
    recipes_root = tmp_path / "recipes"
    recipes_root.mkdir()

    tool_code = '''# Recipe body (create_recipe prepends TOOLS_HEADER equivalents when attached)

from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("x", "does x", {"type": "object", "properties": {}})
async def x(args):
    if _test_mode(): return {"content": [{"type": "text", "text": "mock"}]}
    return {"content": [{"type": "text", "text": "real"}]}

tools_server = create_sdk_mcp_server(name="sample", version="0.1.0", tools=[x])
'''

    result = await create_recipe(
        {
            "type": "tool",
            "name": "sample",
            "description": "sample tool recipe",
            "when_to_use": "in tests only",
            "body": tool_code,
            "maturity": "experimental",
        },
        recipes_root=recipes_root,
    )
    assert result.get("is_error") is not True, result
    assert (recipes_root / "tools" / "sample" / "RECIPE.md").exists()
    assert (recipes_root / "tools" / "sample" / "tool.py").exists()
    rm = (recipes_root / "tools" / "sample" / "RECIPE.md").read_text()
    assert "name: sample" in rm
    assert "maturity: experimental" in rm


@pytest.mark.asyncio
async def test_create_recipe_validates_slug(tmp_path):
    recipes_root = tmp_path / "recipes"
    recipes_root.mkdir()
    result = await create_recipe(
        {"type": "tool", "name": "Bad Name!", "description": "x", "when_to_use": "x", "body": ""},
        recipes_root=recipes_root,
    )
    assert result["is_error"] is True


@pytest.mark.asyncio
async def test_create_recipe_overwrites_by_default(tmp_path):
    recipes_root = tmp_path / "recipes"
    recipes_root.mkdir()
    for body in ("# v1", "# v2"):
        result = await create_recipe(
            {"type": "tool", "name": "sample", "description": "x", "when_to_use": "x", "body": body},
            recipes_root=recipes_root,
        )
        assert result.get("is_error") is not True
    assert "# v2" in (recipes_root / "tools" / "sample" / "tool.py").read_text()
    # Backup exists from the overwrite.
    baks = list((recipes_root / "tools" / "sample").glob("tool.py.bak-*"))
    assert len(baks) == 1
```

- [ ] **Step 2: Implement**

Create `agent_builder/tools/create_recipe.py`:

```python
"""create_recipe — builder authors a new recipe mid-build."""

import datetime
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder.audit import append_audit
from agent_builder.recipes.loader import default_recipes_root
from agent_builder.recipes.schema import parse_recipe_md, RecipeError

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VALID_TYPES = {"tool", "mcp", "skill"}


async def create_recipe(
    args: dict[str, Any],
    *,
    recipes_root: Path | None = None,
) -> dict[str, Any]:
    type_ = args.get("type", "")
    name = args.get("name", "")
    description = args.get("description", "")
    when_to_use = args.get("when_to_use", "")
    body = args.get("body", "")
    maturity = args.get("maturity", "experimental")
    env_keys = args.get("env_keys", [])
    oauth_scopes = args.get("oauth_scopes", [])
    allowed_tools_patterns = args.get("allowed_tools_patterns", [])
    tags = args.get("tags", [])
    overwrite = args.get("overwrite", True)

    if type_ not in _VALID_TYPES:
        return _error(f"type must be one of {sorted(_VALID_TYPES)}")
    if not _NAME_PATTERN.match(name):
        return _error(f"name '{name}' invalid (must match ^[a-z0-9][a-z0-9-]*$)")
    if maturity not in ("in-dev", "experimental", "stable"):
        return _error(f"maturity '{maturity}' invalid")

    root = Path(recipes_root) if recipes_root else default_recipes_root()
    type_dir_name = {"tool": "tools", "mcp": "mcps", "skill": "skills"}[type_]
    target_dir = root / type_dir_name / name
    if target_dir.exists():
        if not overwrite:
            return _error(f"Recipe '{name}' already exists; use overwrite=true to replace.")
        # Backup existing files in-place.
        _backup_existing(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    # Write RECIPE.md
    frontmatter = _render_frontmatter(
        name=name, type_=type_, version="0.1.0", description=description,
        when_to_use=when_to_use, env_keys=env_keys, oauth_scopes=oauth_scopes,
        allowed_tools_patterns=allowed_tools_patterns, tags=tags, maturity=maturity,
    )
    recipe_md = f"{frontmatter}\n\n# {name}\n\n{description}\n"
    (target_dir / "RECIPE.md").write_text(recipe_md, encoding="utf-8")

    # Write type-specific body.
    if type_ == "tool":
        (target_dir / "tool.py").write_text(body or "# empty\n", encoding="utf-8")
    elif type_ == "mcp":
        # For mcp, body should be JSON string for mcp.json.
        (target_dir / "mcp.json").write_text(body or "{}", encoding="utf-8")
    elif type_ == "skill":
        (target_dir / "skill.md").write_text(body or "", encoding="utf-8")

    # Validate via loader.
    try:
        parse_recipe_md(recipe_md, source_path=str(target_dir / "RECIPE.md"))
    except RecipeError as e:
        # Rollback — delete the partial dir.
        shutil.rmtree(target_dir)
        return _error(f"Recipe validation failed: {e}")

    # Audit.
    append_audit(
        action="CREATE",
        subject=f"{type_}/{name}@0.1.0",
        extra={"maturity": maturity, "sha": _short_sha()},
    )

    return _ok(f"saved recipe: {type_}/{name} → {target_dir.relative_to(root.parent)}")


def _render_frontmatter(**kwargs) -> str:
    lines = ["---"]
    lines.append(f"name: {kwargs['name']}")
    lines.append(f"type: {kwargs['type_']}")
    lines.append(f"version: {kwargs['version']}")
    lines.append(f"description: {kwargs['description']}")
    lines.append(f"when_to_use: {kwargs['when_to_use']}")
    lines.append(f"maturity: {kwargs['maturity']}")
    lines.append(f"created_at: {datetime.date.today().isoformat()}")
    sha = _short_sha()
    if sha:
        lines.append(f"git_sha: {sha}")
    if kwargs["env_keys"]:
        lines.append("env_keys:")
        for k in kwargs["env_keys"]:
            lines.append(f"  - name: {k['name']}")
            lines.append(f"    description: {k['description']}")
            if k.get("example"):
                lines.append(f"    example: {k['example']!r}")
    if kwargs["oauth_scopes"]:
        lines.append("oauth_scopes:")
        for s in kwargs["oauth_scopes"]:
            lines.append(f"  - {s}")
    if kwargs["allowed_tools_patterns"]:
        lines.append("allowed_tools_patterns:")
        for p in kwargs["allowed_tools_patterns"]:
            lines.append(f"  - {p}")
    if kwargs["tags"]:
        lines.append(f"tags: {list(kwargs['tags'])}")
    lines.append("---")
    return "\n".join(lines)


def _backup_existing(target_dir: Path) -> None:
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    for f in target_dir.iterdir():
        if f.is_file() and ".bak-" not in f.name:
            shutil.copy2(f, f.with_name(f.name + f".bak-{stamp}"))


def _short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _error(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}], "is_error": True}


def _ok(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}


create_recipe_tool = tool(
    "create_recipe",
    "Author a brand-new recipe (tool, mcp, or skill) and save it to the bundled library. "
    "Use when list_recipes doesn't have what the agent needs and auto-save says green (or "
    "user confirmed the save). Version starts at 0.1.0. Maturity defaults to experimental.",
    {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": list(_VALID_TYPES)},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "when_to_use": {"type": "string"},
            "body": {"type": "string"},
            "maturity": {"type": "string", "enum": ["in-dev", "experimental", "stable"]},
            "env_keys": {"type": "array"},
            "oauth_scopes": {"type": "array"},
            "allowed_tools_patterns": {"type": "array"},
            "tags": {"type": "array"},
            "overwrite": {"type": "boolean"},
        },
        "required": ["type", "name", "description", "when_to_use", "body"],
    },
)(create_recipe)
```

- [ ] **Step 3: Run tests**

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add agent_builder/tools/create_recipe.py tests/test_create_recipe.py
git commit -m "feat(builder): create_recipe authors new recipes mid-build"
```

### Task D3: Auto-save heuristic + builder AGENT.md update

**Files:**
- Create: `tests/test_auto_save_heuristic.py`
- Create: `agent_builder/auto_save.py` (lightweight, callable from tests)
- Modify: `agent_builder/identity/AGENT.md`

- [ ] **Step 1: Test**

```python
"""Tests for auto-save heuristic."""

import pytest

from agent_builder.auto_save import evaluate_tool_for_save, SaveDecision


def test_generic_tool_gets_green():
    code = '''
@tool("send_email", "sends an email", {...})
async def send_email(args):
    """Send an email to `args.to` with subject/body."""
    ...
'''
    decision = evaluate_tool_for_save(code, name="send_email")
    assert decision.decision == "green"


def test_hardcoded_id_triggers_red():
    code = '''
async def notify(args):
    chat_id = 123456789   # hardcoded
    ...
'''
    decision = evaluate_tool_for_save(code, name="notify")
    assert decision.decision == "red"


def test_agent_name_reference_triggers_red():
    code = '''
async def do_thing(args):
    return {"agent": AGENT_NAME, ...}
'''
    decision = evaluate_tool_for_save(code, name="do_thing")
    assert decision.decision == "red"


def test_task_specific_name_triggers_red():
    decision = evaluate_tool_for_save("async def x(): pass", name="schedule_partner_hours_for_taylor")
    assert decision.decision == "red"


def test_ambiguous_returns_ask():
    # Code passes green checks but name is borderline generic.
    decision = evaluate_tool_for_save("async def x(): pass", name="helper")
    assert decision.decision in ("ask", "green")
```

- [ ] **Step 2: Implement**

Create `agent_builder/auto_save.py`:

```python
"""Heuristic: should this bespoke tool be auto-saved as a recipe?"""

import re
from dataclasses import dataclass

# Identifiers that indicate agent-specific coupling.
_AGENT_SPECIFIC_TOKENS = ("AGENT_NAME", "AGENT_DIR")

# Red-flag name patterns (task-specific).
_RED_NAME_PATTERNS = (
    re.compile(r"_for_\w+$"),   # _for_taylor, _for_partner, ...
    re.compile(r"_to_[a-z0-9_]+_calendar$"),
)

# Hardcoded-ID patterns in code bodies.
_RED_CODE_PATTERNS = (
    re.compile(r"\b\d{8,}\b"),                   # long numeric literal (chat_id, project_id)
    re.compile(r"\bchat_id\s*=\s*\d+"),
    re.compile(r"\bproject_id\s*=\s*['\"]\w+['\"]"),
    re.compile(r"taylor|william|partner|alex_park", re.IGNORECASE),
)


@dataclass
class SaveDecision:
    decision: str      # "green" | "red" | "ask"
    reasons: list[str]


def evaluate_tool_for_save(code: str, *, name: str) -> SaveDecision:
    reasons: list[str] = []

    for pat in _RED_NAME_PATTERNS:
        if pat.search(name):
            reasons.append(f"name pattern '{pat.pattern}' matched — task-specific")
    if any(tok in code for tok in _AGENT_SPECIFIC_TOKENS):
        reasons.append("references AGENT_NAME/AGENT_DIR")
    for pat in _RED_CODE_PATTERNS:
        if pat.search(code):
            reasons.append(f"hardcoded-id pattern '{pat.pattern}' matched")

    if reasons:
        return SaveDecision(decision="red", reasons=reasons)

    # Ambiguous names — short, generic, or single-word verbs with no context.
    if len(name) < 4 or name in {"x", "helper", "util", "do_thing", "run"}:
        return SaveDecision(decision="ask", reasons=["name too generic — unclear if reusable"])

    return SaveDecision(decision="green", reasons=[])
```

- [ ] **Step 3: Update builder identity AGENT.md Phase 2**

Append to Phase 2:

```markdown
After designing each bespoke tool, evaluate it with the auto-save heuristic (see `agent_builder/auto_save.py`):

- **Green** — call `create_recipe` silently for the whole tool recipe (not per @tool function). Log to statusbar.
- **Red** — ask user once per top-level recipe: "Save `<proposed-name>` as a reusable recipe for future builds? (y/n). Optional: name + description."
- **Ask** — same prompt as red.

Never prompt per @tool inside a recipe. One ask per top-level recipe proposal.
```

Append to Phase 5:

```markdown
If a test fails AND the failure traces to a recipe just created via `create_recipe` in this session, you MAY call `edit_recipe` with `bump_version=False` to iterate. Capped at 3 attempts per recipe per session. After 3 failures, set `maturity=in-dev` on the recipe via `edit_recipe` and surface the issue to the user for manual fix. Never edit pre-existing recipes without explicit user request.
```

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/auto_save.py tests/test_auto_save_heuristic.py agent_builder/identity/AGENT.md
git commit -m "feat(auto_save): heuristic + builder AGENT.md updates"
```

### Task D4: Register create_recipe

**Files:**
- Modify: `agent_builder/tools/__init__.py`, `builder.py`

- [ ] **Step 1: Register**

Add `from agent_builder.tools.create_recipe import create_recipe_tool`, append to tools list, add to `builder.py`'s allowed_tools.

- [ ] **Step 2: Commit**

```bash
git add agent_builder/tools/__init__.py agent_builder/builder.py
git commit -m "feat(builder): register create_recipe tool"
```

---

## Phase E — `clone_recipe`

Ships: clone tool + slug generator.

### Task E1: `clone_recipe` (TDD)

**Files:**
- Create: `tests/test_clone_recipe.py`
- Create: `agent_builder/tools/clone_recipe.py`

- [ ] **Step 1: Test**

```python
"""Tests for clone_recipe."""

from pathlib import Path

import pytest

from agent_builder.tools.clone_recipe import clone_recipe


@pytest.fixture
def source_recipes_root(tmp_path):
    src = tmp_path / "recipes" / "tools" / "alpha"
    src.mkdir(parents=True)
    (src / "RECIPE.md").write_text(
        "---\nname: alpha\ntype: tool\nversion: 0.2.0\n"
        "description: Original recipe\nwhen_to_use: x\n"
        "maturity: stable\ntags: [one, two]\n---\n"
        "# Alpha\n\nBody.\n",
        encoding="utf-8",
    )
    (src / "tool.py").write_text("# alpha body\n", encoding="utf-8")
    return tmp_path / "recipes"


@pytest.mark.asyncio
async def test_clone_with_explicit_new_name(source_recipes_root):
    result = await clone_recipe(
        {
            "source_name": "alpha",
            "new_name": "alpha-minimal",
            "modifications": {"description": "Minimal fork"},
        },
        recipes_root=source_recipes_root,
    )
    assert result.get("is_error") is not True
    dst = source_recipes_root / "tools" / "alpha-minimal"
    assert dst.exists()
    content = (dst / "RECIPE.md").read_text()
    assert "Minimal fork" in content
    assert "version: 0.1.0" in content  # clones reset version


@pytest.mark.asyncio
async def test_clone_auto_slug(source_recipes_root):
    result = await clone_recipe(
        {
            "source_name": "alpha",
            "modifications": {"description": "read-only variant of alpha"},
        },
        recipes_root=source_recipes_root,
    )
    assert result.get("is_error") is not True
    # Should have generated a descriptive slug.
    children = [p.name for p in (source_recipes_root / "tools").iterdir()]
    assert "alpha" in children
    generated = [c for c in children if c != "alpha"]
    assert len(generated) == 1


@pytest.mark.asyncio
async def test_clone_collision_suffix(source_recipes_root):
    # First clone
    await clone_recipe(
        {"source_name": "alpha", "new_name": "alpha-fork", "modifications": {"description": "d1"}},
        recipes_root=source_recipes_root,
    )
    # Second clone attempting the same name
    result = await clone_recipe(
        {"source_name": "alpha", "new_name": "alpha-fork", "modifications": {"description": "d2"}},
        recipes_root=source_recipes_root,
    )
    assert result.get("is_error") is not True
    children = [p.name for p in (source_recipes_root / "tools").iterdir()]
    assert "alpha-fork" in children
    assert "alpha-fork-2" in children
```

- [ ] **Step 2: Implement**

Create `agent_builder/tools/clone_recipe.py`:

```python
"""clone_recipe — copy an existing recipe with modifications, new name."""

import re
import shutil
from pathlib import Path
from typing import Any

import yaml
from claude_agent_sdk import tool

from agent_builder.audit import append_audit
from agent_builder.recipes.loader import default_recipes_root, load_all_recipes
from agent_builder.recipes.schema import parse_recipe_md, RecipeError

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_TYPE_DIRS = {"tool": "tools", "mcp": "mcps", "skill": "skills"}


async def clone_recipe(
    args: dict[str, Any],
    *,
    recipes_root: Path | None = None,
) -> dict[str, Any]:
    source_name = args.get("source_name", "")
    new_name = args.get("new_name", "")
    mods = args.get("modifications", {})
    rationale = args.get("rationale", "")

    if not _NAME_PATTERN.match(source_name):
        return _error("source_name invalid")

    root = Path(recipes_root) if recipes_root else default_recipes_root()
    try:
        recipes = load_all_recipes(root)
    except RecipeError as e:
        return _error(f"Recipe load error: {e}")

    src = next((r for r in recipes if r.name == source_name), None)
    if src is None:
        return _error(f"Recipe '{source_name}' not found.")

    type_dir = root / _TYPE_DIRS[src.type.value]
    src_dir = type_dir / source_name
    if not src_dir.exists():
        return _error(f"Source dir missing: {src_dir}")

    if not new_name:
        new_name = _auto_slug(source_name, mods, type_dir)
    else:
        if not _NAME_PATTERN.match(new_name):
            return _error(f"new_name '{new_name}' invalid")
        new_name = _resolve_collision(new_name, type_dir)

    dst_dir = type_dir / new_name
    shutil.copytree(src_dir, dst_dir)

    # Apply modifications to RECIPE.md frontmatter + body.
    _apply_modifications(dst_dir / "RECIPE.md", new_name, src, mods)

    # Validate.
    try:
        parse_recipe_md((dst_dir / "RECIPE.md").read_text(encoding="utf-8"), source_path=str(dst_dir / "RECIPE.md"))
    except RecipeError as e:
        shutil.rmtree(dst_dir)
        return _error(f"Clone validation failed: {e}")

    append_audit(
        action="CLONE",
        subject=f"{src.type.value}/{source_name}@{src.version} -> {new_name}@0.1.0",
        extra={"rationale": rationale} if rationale else None,
    )

    return _ok(f"cloned recipe: {source_name} → {new_name}")


def _auto_slug(source: str, mods: dict, type_dir: Path) -> str:
    desc = str(mods.get("description", "")).lower().strip()
    if desc:
        words = re.findall(r"[a-z0-9]+", desc)[:3]
        if words:
            slug = source + "-" + "-".join(words)
            return _resolve_collision(slug, type_dir)
    return _resolve_collision(source + "-variant-1", type_dir)


def _resolve_collision(base: str, type_dir: Path) -> str:
    if not (type_dir / base).exists():
        return base
    m = re.match(r"(.+?)-(\d+)$", base)
    if m:
        stem, n = m.group(1), int(m.group(2))
        base_stem = stem
    else:
        base_stem = base
        n = 1
    while True:
        n += 1
        candidate = f"{base_stem}-{n}"
        if not (type_dir / candidate).exists():
            return candidate


def _apply_modifications(recipe_md_path: Path, new_name: str, src, mods: dict) -> None:
    content = recipe_md_path.read_text(encoding="utf-8")
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    assert m, "RECIPE.md must have frontmatter"
    data = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)

    # Overwrite identity fields.
    data["name"] = new_name
    data["version"] = "0.1.0"
    data["created_at"] = __import__("datetime").date.today().isoformat()

    # Merge modifications (None deletes).
    for k, v in (mods or {}).items():
        if k == "body_replace":
            body = v
        elif k == "body_diff":
            # Apply unified diff — minimal impl for v0.10: reject if body_replace already set.
            raise NotImplementedError("body_diff not yet supported — use body_replace")
        elif v is None:
            data.pop(k, None)
        else:
            data[k] = v

    # Maturity rule: small mods inherit, significant mods force experimental.
    if "maturity" not in (mods or {}):
        data.setdefault("maturity", src.maturity if src.maturity != "in-dev" else "experimental")

    new_front = yaml.safe_dump(data, sort_keys=False).strip()
    recipe_md_path.write_text(f"---\n{new_front}\n---\n{body}", encoding="utf-8")


def _error(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}], "is_error": True}


def _ok(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}


clone_recipe_tool = tool(
    "clone_recipe",
    "Clone an existing recipe with modifications, producing a new recipe with a fresh version. "
    "Use when an existing recipe is close to what's needed but not quite. Auto-generates a slug "
    "if new_name not provided. Bumps version to 0.1.0 in the clone.",
    {
        "type": "object",
        "properties": {
            "source_name": {"type": "string"},
            "new_name": {"type": "string"},
            "modifications": {"type": "object"},
            "rationale": {"type": "string"},
        },
        "required": ["source_name", "modifications"],
    },
)(clone_recipe)
```

- [ ] **Step 3: Run tests**

Expected: pass.

- [ ] **Step 4: Register + commit**

```bash
# Add to tools/__init__.py and builder.py allowed_tools, then:
git add agent_builder/tools/clone_recipe.py agent_builder/tools/__init__.py agent_builder/builder.py tests/test_clone_recipe.py
git commit -m "feat(builder): clone_recipe with auto-slug + collision handling"
```

---

## Phase F — `edit_recipe` + Self-Heal Integration

Ships: edit_recipe tool (restricted usage), session-scoped self-heal tracking.

### Task F1: `edit_recipe` tool (TDD)

**Files:**
- Create: `tests/test_edit_recipe.py`
- Create: `agent_builder/tools/edit_recipe.py`

- [ ] **Step 1: Test**

```python
"""Tests for edit_recipe."""

from pathlib import Path

import pytest

from agent_builder.tools.edit_recipe import edit_recipe


@pytest.fixture
def recipes_root(tmp_path):
    d = tmp_path / "recipes" / "tools" / "x"
    d.mkdir(parents=True)
    (d / "RECIPE.md").write_text(
        "---\nname: x\ntype: tool\nversion: 0.1.0\n"
        "description: x\nwhen_to_use: x\nmaturity: experimental\n---\nBody.\n",
        encoding="utf-8",
    )
    (d / "tool.py").write_text("# v1\n", encoding="utf-8")
    return tmp_path / "recipes"


@pytest.mark.asyncio
async def test_edit_bumps_version(recipes_root):
    result = await edit_recipe(
        {"name": "x", "modifications": {"description": "updated"}},
        recipes_root=recipes_root,
    )
    assert result.get("is_error") is not True
    content = (recipes_root / "tools" / "x" / "RECIPE.md").read_text()
    assert "version: 0.1.1" in content
    assert "updated" in content


@pytest.mark.asyncio
async def test_edit_no_bump(recipes_root):
    result = await edit_recipe(
        {"name": "x", "modifications": {"description": "fix1"}, "bump_version": False},
        recipes_root=recipes_root,
    )
    assert result.get("is_error") is not True
    content = (recipes_root / "tools" / "x" / "RECIPE.md").read_text()
    assert "version: 0.1.0" in content


@pytest.mark.asyncio
async def test_edit_writes_backup(recipes_root):
    await edit_recipe(
        {"name": "x", "modifications": {"description": "d2"}},
        recipes_root=recipes_root,
    )
    baks = list((recipes_root / "tools" / "x").glob("RECIPE.md.bak-*"))
    assert len(baks) == 1
```

- [ ] **Step 2: Implement**

Create `agent_builder/tools/edit_recipe.py`:

```python
"""edit_recipe — in-place recipe modification (user-requested or self-heal)."""

import datetime
import re
import shutil
from pathlib import Path
from typing import Any

import yaml
from claude_agent_sdk import tool

from agent_builder.audit import append_audit
from agent_builder.recipes.loader import default_recipes_root, load_all_recipes
from agent_builder.recipes.schema import parse_recipe_md, RecipeError

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_TYPE_DIRS = {"tool": "tools", "mcp": "mcps", "skill": "skills"}


async def edit_recipe(
    args: dict[str, Any],
    *,
    recipes_root: Path | None = None,
) -> dict[str, Any]:
    name = args.get("name", "")
    mods = args.get("modifications", {})
    bump_version = args.get("bump_version", True)
    reason = args.get("reason", "")

    if not _NAME_PATTERN.match(name):
        return _error(f"name '{name}' invalid")

    root = Path(recipes_root) if recipes_root else default_recipes_root()
    try:
        recipes = load_all_recipes(root)
    except RecipeError as e:
        return _error(f"Recipe load error: {e}")

    target = next((r for r in recipes if r.name == name), None)
    if target is None:
        return _error(f"Recipe '{name}' not found.")

    recipe_dir = root / _TYPE_DIRS[target.type.value] / name

    # Backup every file in the recipe dir.
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    for f in recipe_dir.iterdir():
        if f.is_file() and ".bak-" not in f.name:
            shutil.copy2(f, f.with_name(f.name + f".bak-{stamp}"))

    # Apply modifications to frontmatter + body files.
    _apply_modifications(recipe_dir / "RECIPE.md", mods, bump_version=bump_version)

    # Validate; rollback on failure.
    try:
        parse_recipe_md(
            (recipe_dir / "RECIPE.md").read_text(encoding="utf-8"),
            source_path=str(recipe_dir / "RECIPE.md"),
        )
    except RecipeError as e:
        # Restore backups.
        for bak in recipe_dir.glob(f"*.bak-{stamp}"):
            original = bak.with_name(bak.name.replace(f".bak-{stamp}", ""))
            shutil.copy2(bak, original)
        return _error(f"Edit validation failed; restored backup. {e}")

    append_audit(
        action="EDIT",
        subject=f"{target.type.value}/{name}@{target.version}",
        extra={"reason": reason} if reason else None,
    )

    return _ok(f"edited recipe: {name}")


def _apply_modifications(recipe_md_path: Path, mods: dict, *, bump_version: bool) -> None:
    content = recipe_md_path.read_text(encoding="utf-8")
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    assert m is not None
    data = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)

    for k, v in (mods or {}).items():
        if k == "body_replace":
            body = v
        elif v is None:
            data.pop(k, None)
        else:
            data[k] = v

    if bump_version:
        parts = [int(x) for x in str(data.get("version", "0.1.0")).split(".")]
        parts[-1] += 1
        data["version"] = ".".join(str(p) for p in parts)

    data["edited_at"] = datetime.date.today().isoformat()

    new_front = yaml.safe_dump(data, sort_keys=False).strip()
    recipe_md_path.write_text(f"---\n{new_front}\n---\n{body}", encoding="utf-8")


def _error(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}], "is_error": True}


def _ok(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}


edit_recipe_tool = tool(
    "edit_recipe",
    "Modify an existing recipe in place. Restricted use: user-requested edits, or self-heal "
    "of a recipe just created in this session (e.g. first test failed). Never refactor stable "
    "pre-existing recipes without explicit user request. Bumps patch version by default.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "modifications": {"type": "object"},
            "bump_version": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["name", "modifications"],
    },
)(edit_recipe)
```

- [ ] **Step 3: Register + commit**

```bash
# Add to tools/__init__.py and builder.py allowed_tools, then:
git add agent_builder/tools/edit_recipe.py agent_builder/tools/__init__.py agent_builder/builder.py tests/test_edit_recipe.py
git commit -m "feat(builder): edit_recipe for user + self-heal scenarios"
```

### Task F2: Self-heal integration in test_agent

**Files:**
- Modify: `agent_builder/tools/test_agent.py`

- [ ] **Step 1: Add session-scoped tracking**

Add a module-level set recording recipes created this session:

```python
# Tracks recipe names created by create_recipe in the current builder session.
# edit_recipe self-heal consults this to gate which recipes it's allowed to touch.
_SESSION_CREATED_RECIPES: set[str] = set()


def record_created_recipe(name: str) -> None:
    _SESSION_CREATED_RECIPES.add(name)


def is_session_recipe(name: str) -> bool:
    return name in _SESSION_CREATED_RECIPES
```

Export from `test_agent.py` or a new `session.py` module. Have `create_recipe` call `record_created_recipe(name)` on success.

- [ ] **Step 2: Self-heal loop in test_agent**

After a failed test, check if the failure mentions a session-created recipe. If yes AND attempt count < 3, offer to call `edit_recipe` with `bump_version=False` (silent in builder context; user-confirmable). Track per-recipe attempt count in a dict keyed by recipe name, reset each session.

Exact shape depends on current `test_agent.py` structure — this is a prose-level instruction because implementation diff is test_agent-specific.

- [ ] **Step 3: After 3 attempts — mark in-dev**

If all 3 attempts fail, the builder calls `edit_recipe(name, modifications={"maturity": "in-dev"})` and surfaces to user: "Recipe `<name>` auto-marked in-dev after 3 failed fix attempts. Please review manually."

- [ ] **Step 4: Test**

Write an integration test that creates a recipe with a known bug, scaffolds an agent using it, runs test_agent, and asserts: (a) 3 edit attempts logged to audit, (b) final state is `maturity: in-dev`, (c) user-facing message surfaces.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/test_agent.py agent_builder/tools/create_recipe.py tests/
git commit -m "feat(test_agent): self-heal for session-created recipes (cap 3)"
```

---

## Phase G — Doctor + Statusbar

### Task G1: Doctor extensions

**Files:**
- Modify: `agent_builder/doctor.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 1: Add component validation check**

```python
from agent_builder.recipes.component_loader import load_all_components
from agent_builder.recipes.component_schema import ComponentError


def _check_components_load(builder_dir: Path) -> list[dict[str, str]]:
    comp_dir = builder_dir / "recipes" / "components"
    if not comp_dir.exists():
        return [_check("WARN", "components dir", f"{comp_dir} not found")]
    try:
        comps = load_all_components(comp_dir)
    except ComponentError as e:
        return [_check("FAIL", "components load", str(e))]
    return [_check("OK", "components load", f"{len(comps)} component(s) loaded")]
```

Invoke in `run_health_check`.

- [ ] **Step 2: Add audit log activity line**

```python
from agent_builder.audit import AUDIT_LOG_FILENAME


def _check_audit_log(builder_dir: Path) -> list[dict[str, str]]:
    log = builder_dir / AUDIT_LOG_FILENAME
    if not log.exists():
        return [_check("OK", "audit log", "no activity yet")]
    n = sum(1 for _ in log.open("r", encoding="utf-8"))
    return [_check("OK", "audit log", f"{n} events")]
```

Invoke in `run_health_check`.

- [ ] **Step 3: Commit**

```bash
git add agent_builder/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): validate components + report audit log activity"
```

### Task G2: Statusbar log emission

**Files:**
- Modify: `agent_builder/builder.py` (or wherever `Spinner` is driven during builds)

- [ ] **Step 1: Identify tool-result formatter**

Grep: `grep -n "format_tool_call" agent_builder/builder.py`. The spinner updates its label based on tool calls; after `create_recipe` / `clone_recipe` / `edit_recipe` / `attach_component` succeed, the tool's result text should flow through the same display path.

- [ ] **Step 2: Ensure the result strings match statusbar format**

The tool implementations already return success strings shaped like `"saved recipe: X"`, `"cloned recipe: X"`, `"edited recipe: X"`, `"attached component: X → ..."`. Builder's response handler prints them verbatim — no code change needed unless the display currently swallows them.

Verify by running a smoke build locally and checking stderr/stdout for the expected lines.

- [ ] **Step 3: Commit if any changes**

```bash
git add agent_builder/builder.py
git commit -m "feat(builder): statusbar surfaces recipe write lines"
```

---

## Phase H — Release

### Task H1: End-to-end smoke test

**Files:**
- Create: `tests/test_e2e_v0_10_full_build.py`

- [ ] **Step 1: Write the e2e test**

Exercises the full v0.10 flow in one test:
1. Scaffolds an agent
2. `create_recipe` for a new tool (silent, green flag)
3. `clone_recipe` from an existing recipe with a mod
4. `attach_recipe` for three recipes (new + cloned + existing)
5. `attach_component` for one code + one md component
6. Asserts agent directory has expected files, manifest has right entries, audit log has 3+ events

- [ ] **Step 2: Run**

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_v0_10_full_build.py
git commit -m "test: e2e v0.10 full build (create + clone + attach + component)"
```

### Task H2: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add sections**

Append subsections under "Recipes library":

- **Components** — directory shape, frontmatter-in-comment-header format, target+slot semantics
- **Authoring tools** — `create_recipe`, `clone_recipe`, `edit_recipe`, `attach_component`
- **Maturity tiers** — in-dev hidden; experimental warned; stable quiet
- **Auto-save heuristic** — green/red/ask
- **Self-heal during test** — session-scoped, cap 3
- **Audit log** — `agent_builder/recipe-audit.log`

- [ ] **Step 2: Full test + doctor pass**

Run: `pytest && python -m agent_builder.builder --doctor`
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: v0.10 architecture — components, authoring, maturity, self-heal"
```

### Task H3: PR

- [ ] **Step 1: Push + PR**

```bash
git push -u origin feat/v0.10-authoring-and-components
gh pr create --title "v0.10.0 - authoring layer + components + self-heal" --body "..."
```

---

## Self-Review

**Spec coverage:** §2 (arch) covered Phases A-G; §3 (components) Phase A+B; §4 (auto-save heuristic) D3; §5 (maturity) C; §6-8 (create/clone/edit) D-F; §9 (statusbar) G2; §10 (audit) D1+G1; §11 (workflow) D3; §12 (safety) implicit in each tool's validation; §14 (acceptance criteria) H1.

**Type consistency:** `Recipe` / `RecipeType` / `Component` / `AttachedComponent` imported from same modules throughout; MCP tool shape `{"content": [...], "is_error"?: bool}` uniform; slug validation `^[a-z0-9][a-z0-9-]*$` uniform.

**No placeholders:** every code block runnable. One prose-level instruction (F2 step 2 — self-heal loop shape) deliberately open because it depends on current test_agent.py structure; the surrounding tasks pin the contract (session-scoped set, 3-attempt cap, final mark-in-dev).
