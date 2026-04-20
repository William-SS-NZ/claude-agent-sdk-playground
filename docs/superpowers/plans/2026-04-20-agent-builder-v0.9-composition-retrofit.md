# v0.9 Composition Retrofit — Plan Amendment

> **Applies to:** `2026-04-20-agent-builder-v0.9-recipes-and-server-mode.md`
> **Triggered by:** spec §13 (Amendment — Composition Retrofit)
> **Read alongside the base plan.** This file adds Phase 0 and supersedes specific tasks in Phases B, C, and D.

---

## Phase 0 — Composition Foundation (new, runs before Phase A)

Ships: `.recipe_manifest.json` schema + helpers, `render_agent` module, env-var `AGENT_TEST_MODE`, AGENT.md slot template. After Phase 0, the plumbing to do composition exists but no recipes are defined yet.

Phase 0 lands first. Phase A's recipe schema work still applies; Phase 0 just adds the wiring that Phase A needs to integrate with.

### Task 0.1: Manifest schema + read/write helpers (TDD)

**Files:**
- Create: `tests/test_manifest.py`
- Create: `agent_builder/manifest.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for .recipe_manifest.json read/write/merge."""

import json
from pathlib import Path

import pytest

from agent_builder.manifest import (
    Manifest,
    ManifestError,
    load_manifest,
    save_manifest,
    empty_manifest,
)


def test_empty_manifest_roundtrips(tmp_path):
    m = empty_manifest(agent_name="x", builder_version="0.9.0")
    save_manifest(tmp_path / ".recipe_manifest.json", m)
    loaded = load_manifest(tmp_path / ".recipe_manifest.json")
    assert loaded.agent_name == "x"
    assert loaded.builder_version == "0.9.0"
    assert loaded.recipes == []
    assert loaded.components == []


def test_manifest_rejects_bad_shape(tmp_path):
    (tmp_path / ".recipe_manifest.json").write_text('{"manifest_version": 99}', encoding="utf-8")
    with pytest.raises(ManifestError, match="manifest_version"):
        load_manifest(tmp_path / ".recipe_manifest.json")


def test_manifest_rejects_duplicate_recipe_names(tmp_path):
    bad = {
        "manifest_version": 1,
        "agent_name": "x",
        "builder_version": "0.9.0",
        "recipes": [
            {"name": "telegram-poll", "type": "tool", "version": "0.1.0", "attached_at": "2026-04-20"},
            {"name": "telegram-poll", "type": "tool", "version": "0.2.0", "attached_at": "2026-04-20"},
        ],
        "components": [],
    }
    (tmp_path / ".recipe_manifest.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ManifestError, match="duplicate"):
        load_manifest(tmp_path / ".recipe_manifest.json")


def test_manifest_missing_file_returns_empty(tmp_path):
    m = load_manifest(tmp_path / "nonexistent.json", agent_name="x", builder_version="0.9.0")
    assert m.recipes == []
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_manifest.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `agent_builder/manifest.py`:

```python
"""Agent manifest — source of truth for attached recipes and components."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = ".recipe_manifest.json"
CURRENT_MANIFEST_VERSION = 1


class ManifestError(ValueError):
    """Raised on malformed or incompatible manifests."""


@dataclass
class AttachedRecipe:
    name: str
    type: str           # "tool" | "mcp" | "skill"
    version: str
    attached_at: str    # ISO date (YYYY-MM-DD)
    git_sha: str = ""   # short 7-char hash, optional


@dataclass
class AttachedComponent:
    name: str
    version: str
    target: str         # e.g. "agent.py" | "tools.py" | "AGENT.md:slot=workflow"
    attached_at: str
    git_sha: str = ""


@dataclass
class Manifest:
    manifest_version: int = CURRENT_MANIFEST_VERSION
    agent_name: str = ""
    builder_version: str = ""
    recipes: list[AttachedRecipe] = field(default_factory=list)
    components: list[AttachedComponent] = field(default_factory=list)


def empty_manifest(agent_name: str, builder_version: str) -> Manifest:
    return Manifest(agent_name=agent_name, builder_version=builder_version)


def load_manifest(path: Path, *, agent_name: str = "", builder_version: str = "") -> Manifest:
    path = Path(path)
    if not path.exists():
        return empty_manifest(agent_name=agent_name, builder_version=builder_version)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ManifestError(f"{path}: not valid JSON: {e}") from e

    if data.get("manifest_version") != CURRENT_MANIFEST_VERSION:
        raise ManifestError(
            f"{path}: manifest_version {data.get('manifest_version')!r} not supported "
            f"(this builder expects {CURRENT_MANIFEST_VERSION})"
        )

    recipes = [AttachedRecipe(**r) for r in data.get("recipes", [])]
    _check_unique(recipes, "recipe", path)
    components = [AttachedComponent(**c) for c in data.get("components", [])]
    _check_unique(components, "component", path)

    return Manifest(
        manifest_version=data["manifest_version"],
        agent_name=data.get("agent_name", ""),
        builder_version=data.get("builder_version", ""),
        recipes=recipes,
        components=components,
    )


def save_manifest(path: Path, manifest: Manifest) -> None:
    path = Path(path)
    data = asdict(manifest)
    # Sort recipes + components alphabetically for stable diffs.
    data["recipes"] = sorted(data["recipes"], key=lambda r: r["name"])
    data["components"] = sorted(data["components"], key=lambda c: (c["target"], c["name"]))
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _check_unique(items: list, label: str, path: Path) -> None:
    seen: set[str] = set()
    for item in items:
        key = getattr(item, "name")
        if label == "component":
            key = f"{item.target}::{item.name}"
        if key in seen:
            raise ManifestError(f"{path}: duplicate {label} {key!r}")
        seen.add(key)
```

- [ ] **Step 4: Run tests**

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/manifest.py tests/test_manifest.py
git commit -m "feat(manifest): schema, load/save, duplicate detection"
```

### Task 0.2: `AGENT_TEST_MODE` env var + TOOLS_HEADER update

**Files:**
- Modify: `agent_builder/tools/write_tools.py` (TOOLS_HEADER)
- Modify: `agent_builder/tools/test_agent.py` (flip env var, not file)

- [ ] **Step 1: Find the TOOLS_HEADER constant**

Grep: `grep -n "TOOLS_HEADER" agent_builder/tools/write_tools.py`. Note its current shape.

- [ ] **Step 2: Update TOOLS_HEADER**

Replace the `TEST_MODE = False` line with an env-var helper:

```python
TOOLS_HEADER = """\
\"\"\"Tools for {{agent_name}} — generated by Agent Builder.

Agent-bespoke tools only. Recipe-sourced tools live in ./_recipes/ and are
auto-registered via agent.py.
\"\"\"

import os

from claude_agent_sdk import tool, create_sdk_mcp_server


def _test_mode() -> bool:
    \"\"\"Return True when AGENT_TEST_MODE env is set — flipped by test_agent.\"\"\"
    return os.environ.get(\"AGENT_TEST_MODE\") == \"1\"

"""
```

- [ ] **Step 3: Update test_agent to flip env, not file**

Find and replace the current TEST_MODE-flip logic. Before calling `query()`:

```python
os.environ["AGENT_TEST_MODE"] = "1"
try:
    # existing query() / run logic
    ...
finally:
    os.environ.pop("AGENT_TEST_MODE", None)
```

Remove the regex-replace-file code that flipped `TEST_MODE = False` → `TEST_MODE = True`.

- [ ] **Step 4: Update generated-agent contract docs in CLAUDE.md**

Under "Generated-agent contract", change:

> - Include an `if TEST_MODE:` branch at the top returning mock data (so `test_agent` can exercise them offline)

to:

> - Include an `if _test_mode():` branch at the top returning mock data (so `test_agent` can exercise them offline). `_test_mode()` reads `AGENT_TEST_MODE` env var; `TOOLS_HEADER` provides the helper.

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: any existing tests using the old TEST_MODE flip need updates. Fix them to flip env var instead.

- [ ] **Step 6: Commit**

```bash
git add agent_builder/tools/write_tools.py agent_builder/tools/test_agent.py CLAUDE.md tests/
git commit -m "refactor(test_mode): env var AGENT_TEST_MODE replaces file-level flag"
```

### Task 0.3: `render_agent` module (TDD)

**Files:**
- Create: `tests/test_render.py`
- Create: `agent_builder/render.py`
- Modify: `agent_builder/templates/agent_main.py.tmpl` — add four new placeholders

- [ ] **Step 1: Write the failing test**

```python
"""Tests for render_agent — rebuilds agent.py + AGENT.md from manifest."""

import json
from pathlib import Path

import pytest

from agent_builder.render import render_agent
from agent_builder.manifest import Manifest, AttachedRecipe, save_manifest


def _scaffolded_agent(tmp_path: Path) -> Path:
    """Helper: produce a just-scaffolded agent dir with minimal file surface."""
    from agent_builder.tools.scaffold import scaffold_agent
    import asyncio
    out = tmp_path / "output"
    out.mkdir()
    asyncio.run(scaffold_agent({"agent_name": "a", "description": "x"}, output_base=str(out)))
    return out / "a"


@pytest.mark.asyncio
async def test_render_with_empty_manifest_produces_valid_agent_py(tmp_path):
    agent_dir = _scaffolded_agent(tmp_path)
    manifest = Manifest(agent_name="a", builder_version="0.9.0")
    save_manifest(agent_dir / ".recipe_manifest.json", manifest)

    render_agent(agent_dir)

    agent_py = (agent_dir / "agent.py").read_text()
    assert "RECIPE_PINS = {}" in agent_py
    assert '"agent_tools": tools_server' in agent_py
    # No recipe imports block
    assert "# --- recipe servers ---" in agent_py  # banner still present, empty body below
    # Placeholders fully substituted
    assert "{{" not in agent_py


@pytest.mark.asyncio
async def test_render_with_tool_recipe_emits_import_and_server_entry(tmp_path):
    agent_dir = _scaffolded_agent(tmp_path)
    (agent_dir / "_recipes").mkdir()
    (agent_dir / "_recipes" / "telegram_poll.py").write_text(
        'from claude_agent_sdk import create_sdk_mcp_server\n'
        'tools_server = create_sdk_mcp_server(name="telegram_poll", version="0.1.0", tools=[])\n',
        encoding="utf-8",
    )
    manifest = Manifest(
        agent_name="a",
        builder_version="0.9.0",
        recipes=[AttachedRecipe(
            name="telegram-poll", type="tool", version="0.1.0", attached_at="2026-04-20",
        )],
    )
    save_manifest(agent_dir / ".recipe_manifest.json", manifest)

    render_agent(agent_dir)

    agent_py = (agent_dir / "agent.py").read_text()
    assert "from _recipes.telegram_poll import tools_server as telegram_poll_server" in agent_py
    assert '"telegram_poll": telegram_poll_server' in agent_py
    assert '"telegram-poll": "0.1.0"' in agent_py  # in RECIPE_PINS


def test_render_preserves_user_additions_slot(tmp_path):
    agent_dir = _scaffolded_agent(tmp_path)
    manifest = Manifest(agent_name="a", builder_version="0.9.0")
    save_manifest(agent_dir / ".recipe_manifest.json", manifest)
    # Seed AGENT.md with user content in the slot
    (agent_dir / "AGENT.md").write_text(
        "# Agent\n\n"
        "## Purpose\nRendered.\n\n"
        "<!-- SLOT: builder_agent_additions -->\n"
        "<!-- /SLOT: builder_agent_additions -->\n\n"
        "<!-- SLOT: user_additions -->\n"
        "Hand-written note that must survive.\n"
        "<!-- /SLOT: user_additions -->\n",
        encoding="utf-8",
    )

    render_agent(agent_dir)

    content = (agent_dir / "AGENT.md").read_text()
    assert "Hand-written note that must survive." in content
```

- [ ] **Step 2: Add four new placeholders to agent_main.py.tmpl**

Update the `mcp_servers` section and add a recipe imports block near the other imports:

```python
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    HookMatcher,
)

# --- recipe servers ---
{{recipe_imports_block}}
# --- /recipe servers ---
```

Update `mcp_servers` dict:

```python
    mcp_servers={
        "agent_tools": tools_server,
        {{recipe_servers_block}}
        {{external_mcp_block}}
    },
```

`{{recipe_pins_block}}` already added in base-plan Task B1.

- [ ] **Step 3: Implement render.py**

```python
"""render_agent — rebuilds agent.py and AGENT.md from an agent's manifest."""

import json
import re
from pathlib import Path

from agent_builder.manifest import Manifest, MANIFEST_FILENAME, load_manifest

TEMPLATES_DIR = Path(__file__).parent / "templates"
_SLOT_PATTERN = re.compile(
    r"<!-- SLOT: (?P<name>\S+) -->(?P<body>.*?)<!-- /SLOT: \S+ -->",
    re.DOTALL,
)

PRESERVED_SLOTS = ("builder_agent_additions", "user_additions")


def render_agent(agent_dir: Path) -> None:
    """Regenerate agent.py + AGENT.md from .recipe_manifest.json."""
    agent_dir = Path(agent_dir)
    manifest_path = agent_dir / MANIFEST_FILENAME
    manifest = load_manifest(manifest_path, agent_name=agent_dir.name)

    _render_agent_py(agent_dir, manifest)
    _render_agent_md(agent_dir, manifest)


def _slug_to_module(slug: str) -> str:
    return slug.replace("-", "_")


def _render_agent_py(agent_dir: Path, manifest: Manifest) -> None:
    agent_py = agent_dir / "agent.py"
    if not agent_py.exists():
        return  # scaffold hasn't written yet; render is a no-op

    content = agent_py.read_text(encoding="utf-8")

    # Build replacement blocks from manifest
    tool_recipes = sorted([r for r in manifest.recipes if r.type == "tool"], key=lambda r: r.name)
    mcp_recipes = sorted([r for r in manifest.recipes if r.type == "mcp"], key=lambda r: r.name)

    imports_lines = []
    server_entries = []
    for r in tool_recipes:
        mod = _slug_to_module(r.name)
        imports_lines.append(
            f"from _recipes.{mod} import tools_server as {mod}_server"
        )
        server_entries.append(f'"{mod}": {mod}_server,')
    imports_block = "\n".join(imports_lines)
    servers_block = "\n        ".join(server_entries)

    # external_mcp_block from mcp-type recipes (reads each recipe's mcp.json via
    # attach-time copy stored alongside _recipes/ as <slug>.mcp.json for renders).
    # Implementation note: attach_recipe copies the mcp.json sibling into
    # agent_dir/_recipes/<slug>.mcp.json so render doesn't need recipe-library access.
    external_entries = []
    for r in mcp_recipes:
        mcp_json = agent_dir / "_recipes" / f"{_slug_to_module(r.name)}.mcp.json"
        if mcp_json.exists():
            cfg = json.loads(mcp_json.read_text(encoding="utf-8"))
            cfg.pop("env_passthrough", None)
            external_entries.append(f'"{_slug_to_module(r.name)}": {repr(cfg)},')
    external_block = "\n        ".join(external_entries)

    pins_dict = {r.name: r.version for r in manifest.recipes}
    pins_block = "RECIPE_PINS = " + json.dumps(dict(sorted(pins_dict.items())))

    # Atomic substitution — all four blocks filled from manifest state.
    content = _replace_block(content, "recipe_imports_block", imports_block)
    content = _replace_block(content, "recipe_servers_block", servers_block)
    content = _replace_block(content, "external_mcp_block", external_block)
    content = _replace_block(content, "recipe_pins_block", pins_block)

    agent_py.write_text(content, encoding="utf-8")


def _replace_block(content: str, block_name: str, new_value: str) -> str:
    """Replace both unfilled {{X}} placeholders AND re-rendered previous values.

    Re-renders stamp a `# <block_name>-start` / `# <block_name>-end` marker pair
    around each block so subsequent renders find and replace them deterministically.
    """
    start_marker = f"# <<{block_name}>>"
    end_marker = f"# <</{block_name}>>"

    block_body = f"{start_marker}\n{new_value}\n{end_marker}"

    placeholder = "{{" + block_name + "}}"
    if placeholder in content:
        return content.replace(placeholder, block_body, 1)

    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    return pattern.sub(block_body, content, count=1)


def _render_agent_md(agent_dir: Path, manifest: Manifest) -> None:
    agent_md = agent_dir / "AGENT.md"
    template_path = TEMPLATES_DIR / "agent_md.tmpl"
    if not template_path.exists():
        return  # Task 0.4 adds this; render is a no-op until then.

    # Preserve the two user-owned slots from the existing AGENT.md.
    preserved: dict[str, str] = {}
    if agent_md.exists():
        existing = agent_md.read_text(encoding="utf-8")
        for m in _SLOT_PATTERN.finditer(existing):
            if m.group("name") in PRESERVED_SLOTS:
                preserved[m.group("name")] = m.group("body")

    template = template_path.read_text(encoding="utf-8")

    # Rendered slots are supplied by skill recipes (Phase G / future); for v0.9
    # every rendered slot is empty unless the agent's authoring step populated it.
    # Phase 0 ships the mechanism; skill-recipe integration is deferred.
    for slot in ("purpose", "workflow", "constraints", "tools_reference", "examples", "first_run_setup"):
        template = template.replace(f"{{{{slot:{slot}}}}}", "")

    for slot in PRESERVED_SLOTS:
        body = preserved.get(slot, "")
        marker_block = f"<!-- SLOT: {slot} -->{body}<!-- /SLOT: {slot} -->"
        template = template.replace(f"{{{{slot:{slot}}}}}", marker_block)

    template = template.replace("{{agent_name}}", manifest.agent_name)
    agent_md.write_text(template, encoding="utf-8")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_render.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/render.py agent_builder/templates/agent_main.py.tmpl tests/test_render.py
git commit -m "feat(render): regenerate agent.py + AGENT.md from manifest"
```

### Task 0.4: AGENT.md slot template

**Files:**
- Create: `agent_builder/templates/agent_md.tmpl`

- [ ] **Step 1: Write the template**

```markdown
# {{agent_name}}

## Purpose

{{slot:purpose}}

## Workflow

{{slot:workflow}}

## Constraints

{{slot:constraints}}

## Tools

{{slot:tools_reference}}

## Examples

{{slot:examples}}

## First-run setup

{{slot:first_run_setup}}

---

{{slot:builder_agent_additions}}

{{slot:user_additions}}
```

- [ ] **Step 2: Doctor check**

Add to `agent_builder/doctor.py` — verify template has all expected slot markers:

```python
EXPECTED_AGENT_MD_SLOTS = (
    "{{slot:purpose}}",
    "{{slot:workflow}}",
    "{{slot:constraints}}",
    "{{slot:tools_reference}}",
    "{{slot:examples}}",
    "{{slot:first_run_setup}}",
    "{{slot:builder_agent_additions}}",
    "{{slot:user_additions}}",
)


def _check_agent_md_template(builder_dir: Path) -> list[dict[str, str]]:
    path = builder_dir / "templates" / "agent_md.tmpl"
    if not path.exists():
        return [_check("FAIL", "agent_md template", f"missing: {path}")]
    content = path.read_text(encoding="utf-8")
    missing = [s for s in EXPECTED_AGENT_MD_SLOTS if s not in content]
    if missing:
        return [_check("FAIL", "agent_md slots", f"missing slots: {missing}")]
    return [_check("OK", "agent_md slots", f"all {len(EXPECTED_AGENT_MD_SLOTS)} present")]
```

Invoke in `run_health_check`.

- [ ] **Step 3: Commit**

```bash
git add agent_builder/templates/agent_md.tmpl agent_builder/doctor.py
git commit -m "feat(templates): AGENT.md slot template + doctor check"
```

---

## Supersedes — base plan Task B1

Base plan §B1 adds only `{{recipe_pins_block}}` to agent_main.py.tmpl. **Superseded by Task 0.3** which adds four placeholders (`{{recipe_imports_block}}`, `{{recipe_servers_block}}`, `{{external_mcp_block}}`, `{{recipe_pins_block}}`), all rendered from the manifest.

`REQUIRED_PLACEHOLDERS_COMMON` grows to include all four. Substitution at scaffold time emits **empty values** for all four (empty manifest), marking them with the start/end block markers that `_replace_block` uses for future rerenders:

```python
    .replace("{{recipe_imports_block}}",  "# <<recipe_imports_block>>\n# <</recipe_imports_block>>")
    .replace("{{recipe_servers_block}}",  "# <<recipe_servers_block>>\n# <</recipe_servers_block>>")
    .replace("{{external_mcp_block}}",    "# <<external_mcp_block>>\n# <</external_mcp_block>>")
    .replace("{{recipe_pins_block}}",     "# <<recipe_pins_block>>\nRECIPE_PINS = {}\n# <</recipe_pins_block>>")
```

`render_agent` finds these markers and rewrites between them on every subsequent rerender — deterministic, idempotent, independent of file length.

Scaffold must also write an empty `.recipe_manifest.json` into the new agent dir so later attach calls have a file to read. Add to `scaffold.py`:

```python
from agent_builder.manifest import empty_manifest, save_manifest
save_manifest(agent_dir / MANIFEST_FILENAME, empty_manifest(agent_name=agent_name, builder_version=_builder_version.__version__))
```

---

## Supersedes — base plan Task B2

Base plan §B2 implements `_attach_tool_recipe` by appending tool code into the agent's `tools.py` with a version header. **Superseded** by composition-based version:

```python
def _attach_tool_recipe(recipe: Recipe, agent_dir: Path, recipes_root: Path) -> dict[str, Any]:
    from agent_builder.render import render_agent
    from agent_builder.manifest import AttachedRecipe, load_manifest, save_manifest, MANIFEST_FILENAME

    # Copy recipe source into agent's _recipes/ dir.
    recipes_dir = agent_dir / "_recipes"
    recipes_dir.mkdir(exist_ok=True)
    src = recipes_root / "tools" / recipe.name / "tool.py"
    dst = recipes_dir / f"{recipe.name.replace('-', '_')}.py"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    # Update manifest (idempotent on recipe name).
    manifest_path = agent_dir / MANIFEST_FILENAME
    manifest = load_manifest(manifest_path, agent_name=agent_dir.name)
    existing = next((r for r in manifest.recipes if r.name == recipe.name), None)
    if existing is not None:
        if existing.version == recipe.version:
            return _ok(f"Recipe '{recipe.name}@{recipe.version}' already attached.")
        # Version changed — replace
        manifest.recipes = [r for r in manifest.recipes if r.name != recipe.name]
    manifest.recipes.append(AttachedRecipe(
        name=recipe.name,
        type="tool",
        version=recipe.version,
        attached_at=_today_iso(),
        git_sha=_short_sha(),
    ))
    save_manifest(manifest_path, manifest)

    # Regenerate agent.py from manifest.
    render_agent(agent_dir)

    return _ok(f"Attached tool recipe '{recipe.name}@{recipe.version}' via composition.")
```

Add two helpers to `attach_recipe.py`:

```python
import datetime
import subprocess

def _today_iso() -> str:
    return datetime.date.today().isoformat()

def _short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
```

**Test adjustments:** Task B2's four existing tests need shape updates:

- `test_attach_tool_recipe_copies_code` — assert `_recipes/hello_world.py` exists and contains `async def hello`; assert `agent.py` has the `from _recipes.hello_world import tools_server as hello_world_server` import line.
- `test_attach_tool_recipe_idempotent` — compare `.recipe_manifest.json` content before and after; assert identical. Also assert `_recipes/hello_world.py` mtime unchanged on second attach (early-return).
- `test_attach_unknown_recipe_errors` — unchanged.
- `test_attach_rejects_path_traversal` — unchanged.

The recipe's `tool.py` must itself end with a `tools_server = create_sdk_mcp_server(...)` call — the existing `hello-world` fixture already does this. Update the fixture's `RECIPE.md` to reflect that the tool registers its own server (note in the body).

---

## Supersedes — base plan Task C5

Base plan §C5 implements `_maybe_wire_poll_source` by text-replacing `_stub_poll_source()` in `agent.py`. **Superseded** by manifest-driven wiring:

New field in `Manifest`:

```python
@dataclass
class Manifest:
    manifest_version: int = CURRENT_MANIFEST_VERSION
    agent_name: str = ""
    builder_version: str = ""
    recipes: list[AttachedRecipe] = field(default_factory=list)
    components: list[AttachedComponent] = field(default_factory=list)
    poll_source: str = ""   # e.g. "telegram-poll" — the recipe providing telegram_poll_source
```

Tool recipes with `poll_source: true` (new frontmatter field) mark themselves as poll-capable. On attach, set `manifest.poll_source = recipe.name` (fail if already set to a different recipe — only one poll source per agent).

`render_agent` uses this to fill `{{poll_source_import}}` and `{{poll_source_expr}}`:

```python
def _poll_source_blocks(manifest: Manifest) -> tuple[str, str]:
    if not manifest.poll_source:
        return ("", "_stub_poll_source()  # attach a poll-capable recipe to replace")
    mod = manifest.poll_source.replace("-", "_")
    return (
        f"from _recipes.{mod} import telegram_poll_source  # poll source (recipe: {manifest.poll_source})",
        f"telegram_poll_source()",
    )
```

(Generalizable: poll-capable recipes could declare the function name they expose; for v0.9 telegram-poll is the only one so hardcode to `telegram_poll_source`. v0.10 reads it from the recipe's frontmatter.)

`_stub_poll_source` impl still lives inside `agent.py` for the no-recipe-attached case (scaffold injects it for poll mode).

**Test adjustments:** `test_attach_telegram_poll_fills_stubs` is largely the same but assertions point at render output — `from _recipes.telegram_poll import telegram_poll_source` as the import line, etc.

---

## Supersedes — base plan Task D3

Base plan §D3's `_attach_mcp_recipe` edits `agent.py` directly via `_merge_mcp_server_entry` (regex-replace). **Superseded** by composition:

```python
def _attach_mcp_recipe(recipe: Recipe, agent_dir: Path, recipes_root: Path) -> dict[str, Any]:
    from agent_builder.render import render_agent
    from agent_builder.manifest import AttachedRecipe, load_manifest, save_manifest, MANIFEST_FILENAME

    # Copy the recipe's mcp.json sibling into agent_dir/_recipes/<slug>.mcp.json for render access.
    recipes_dir = agent_dir / "_recipes"
    recipes_dir.mkdir(exist_ok=True)
    src_mcp = recipes_root / "mcps" / recipe.name / "mcp.json"
    mcp_cfg = json.loads(src_mcp.read_text(encoding="utf-8"))

    # Validate env_passthrough against declared env_keys (same as base plan).
    passthrough = mcp_cfg.get("env_passthrough", [])
    declared = {k.name for k in recipe.env_keys}
    unknown = [k for k in passthrough if k not in declared]
    if unknown:
        return _error(f"mcp.json env_passthrough references undeclared env_keys: {unknown}")

    # Write the config alongside _recipes for render to pick up.
    dst_mcp = recipes_dir / f"{recipe.name.replace('-', '_')}.mcp.json"
    dst_mcp.write_text(json.dumps(mcp_cfg, indent=2), encoding="utf-8")

    # .env.example merge — unchanged from base plan.
    try:
        _merge_env_example(agent_dir / ".env.example", recipe)
    except RuntimeError as e:
        return _error(str(e))

    # OAuth helper — unchanged.
    if recipe.oauth_scopes:
        try:
            _render_setup_auth(recipe, agent_dir, recipes_root)
        except RuntimeError as e:
            return _error(str(e))

    # Update manifest + rerender.
    manifest_path = agent_dir / MANIFEST_FILENAME
    manifest = load_manifest(manifest_path, agent_name=agent_dir.name)
    manifest.recipes = [r for r in manifest.recipes if r.name != recipe.name]
    manifest.recipes.append(AttachedRecipe(
        name=recipe.name, type="mcp", version=recipe.version,
        attached_at=_today_iso(), git_sha=_short_sha(),
    ))
    save_manifest(manifest_path, manifest)

    render_agent(agent_dir)

    return _ok(f"Attached mcp recipe '{recipe.name}@{recipe.version}'.")
```

The `_merge_mcp_server_entry` helper is removed (render replaces its job).

**Test adjustments:** `test_attach_mcp_recipe_inlines_into_agent_py` still works — render puts the mcp entry in agent.py via `{{external_mcp_block}}` substitution. `test_attach_mcp_recipe_idempotent` now also asserts manifest content stable.

---

## Supersedes — nothing in Phase E

Phase E tasks (E1 through E8) are unchanged. OAuth helper rendering, google-calendar recipe authoring, docs, handoff banner, e2e smoke, and PR all work identically.

**One small add to E6** — the e2e smoke test additionally asserts the manifest shape:

```python
    manifest = json.loads((agent_dir / ".recipe_manifest.json").read_text())
    assert len(manifest["recipes"]) == 2
    assert {r["name"] for r in manifest["recipes"]} == {"telegram-poll", "google-calendar"}
```

---

## Self-Review

**Architectural consistency:** composition model used uniformly for tool, mcp, and (future) skill recipes. No anchor-based insertion anywhere in v0.9. Render is the only writer to `agent.py` / `AGENT.md` after scaffold.

**Spec coverage:** all §13.1–13.8 items in the amended spec are addressed — manifest (Task 0.1), render (Task 0.3), env var TEST_MODE (Task 0.2), AGENT.md slots (Task 0.4), supersession of B1/B2/C5/D3, acceptance checklist in E6.

**Backwards compatibility:** builder agents built with pre-v0.9 builders don't have a manifest. When `attach_recipe` runs against them, `load_manifest` returns empty — attach proceeds, then render finds no start/end markers in their `agent.py` and replaces the raw `{{...}}` placeholders (which don't exist in old agents either). **Gap:** attach_recipe against a pre-v0.9 agent will fail silently (placeholders missing, markers missing → no-op). Mitigation: attach_recipe detects this case and returns `is_error` with a clear message: "agent `<name>` was generated with builder <version>; rescaffold required for v0.9 recipe attachment."

**No placeholders in this patch:** every code block is runnable or a specific delta. Task 0.1 through 0.4 complete before Phase A runs.
