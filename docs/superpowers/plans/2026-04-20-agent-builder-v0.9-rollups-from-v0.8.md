# v0.9 Rollups from v0.8 Backlog — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Six carry-over items from `docs/next-release-plan.md` (the unshipped v0.8.0 plan) and `TODO.md` that belong in v0.9 — either because they synergise with v0.9's composition/authoring work, or because they're quick wins that clean up code the v0.9 plan touches anyway.

**Not included (deliberately):** complexity refactors (v0.8 plan 2.2), release mechanics (3.1 + 3.2 — do at PyPI time), polish items (TODO.md "Polish / nice-to-have").

**Already covered elsewhere:** `AGENT_TEST_MODE` env var (v0.8 plan 1.1) — lands as Task 0.2 in the v0.9 composition retrofit. No duplicate task here.

**Branch:** `feat/v0.9-recipes-and-server-mode` — same branch as v0.9 work.

**Sequencing:**
- Tasks R1–R4 are standalone and can land in any order, any time.
- Task R5 (path validators) is best done **before** v0.9 Phases B–E so the new `attach_recipe` / `attach_component` / `create_recipe` etc. tools pick up the shared validator rather than duplicating the inline pattern.
- Task R6 (utils dedupe) is best done **after** v0.9 Phase 0 introduces the second template (`agent_poll.py.tmpl`), so the dedupe covers both templates in one shot. Place it at the Phase 0 → Phase A boundary.

---

## Task R1: Gate `WebFetch` / `WebSearch` behind `ENABLE_WEB_TOOLS=1`

Safety hardening ahead of any future public build. Public users pasting URLs into discovery should not trigger arbitrary outbound fetches without explicit opt-in.

**Files:**
- Modify: `agent_builder/builder.py` (`_build_options` — conditional web-tool append)
- Modify: `agent_builder/identity/AGENT.md` (Phase 2 note)
- Modify: `README.md` (env var documented)
- Modify: `tests/test_builder_cli.py` (or wherever `_build_options` is exercised) — add env-var toggle tests

- [ ] **Step 1: Write failing test**

Add to `tests/test_builder_cli.py` (or the file that tests `_build_options`):

```python
import os

import pytest


def test_web_tools_off_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_WEB_TOOLS", raising=False)
    from agent_builder.builder import _build_options
    opts = _build_options(verbose=False)
    assert "WebFetch" not in opts.allowed_tools
    assert "WebSearch" not in opts.allowed_tools


def test_web_tools_on_when_env_set(monkeypatch):
    monkeypatch.setenv("ENABLE_WEB_TOOLS", "1")
    from agent_builder.builder import _build_options
    opts = _build_options(verbose=False)
    assert "WebFetch" in opts.allowed_tools
    assert "WebSearch" in opts.allowed_tools


def test_web_tools_off_when_env_set_to_other_value(monkeypatch):
    monkeypatch.setenv("ENABLE_WEB_TOOLS", "0")
    from agent_builder.builder import _build_options
    opts = _build_options(verbose=False)
    assert "WebFetch" not in opts.allowed_tools
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_builder_cli.py -k web_tools -v`
Expected: FAIL — current `_build_options` always includes web tools.

- [ ] **Step 3: Gate the web tools**

Grep: `grep -n "WebFetch\|WebSearch" agent_builder/builder.py`. Edit the block where they get added to `allowed_tools`:

```python
import os

# existing allowed_tools list assembly ...
if os.environ.get("ENABLE_WEB_TOOLS") == "1":
    allowed_tools.extend(["WebFetch", "WebSearch"])
```

- [ ] **Step 4: Update builder AGENT.md Phase 2 note**

Find the existing Phase 2 paragraph that tells the builder it can use WebFetch/WebSearch. Append:

```markdown
**Availability:** `WebFetch` and `WebSearch` are gated behind `ENABLE_WEB_TOOLS=1`. If you try to call them and they're not in your tool list, tell the user the env var needs to be set to enable web research.
```

- [ ] **Step 5: README note**

Add to README.md under the "Authentication" or "Running" section:

```markdown
## Web tools (opt-in)

`WebFetch` and `WebSearch` are off by default in the builder's tool list. Enable them by setting `ENABLE_WEB_TOOLS=1` in your environment before launching the builder. Use cases: the builder fetches current API docs during Phase 2 design research. Leave them off for public / untrusted environments.
```

- [ ] **Step 6: Run tests**

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add agent_builder/builder.py agent_builder/identity/AGENT.md README.md tests/test_builder_cli.py
git commit -m "feat(safety): gate WebFetch/WebSearch behind ENABLE_WEB_TOOLS=1"
```

---

## Task R2: Lazy `self-heal.log` FileHandler

Module-level `FileHandler` opens the real log file at import time — test runs leak handles and pollute the real `agent_builder/self-heal.log`.

**Files:**
- Modify: `agent_builder/tools/self_heal.py`
- Modify: `tests/test_self_heal.py` (or wherever self_heal is tested)

- [ ] **Step 1: Write failing test**

```python
def test_self_heal_importing_does_not_open_log_handler():
    import importlib
    import agent_builder.tools.self_heal as sh
    importlib.reload(sh)  # fresh import

    # After import, no FileHandler should be attached to the audit logger.
    handlers = [h for h in sh._audit_logger.handlers]
    file_handlers = [h for h in handlers if hasattr(h, "baseFilename")]
    assert file_handlers == [], f"FileHandler leaked at import: {file_handlers}"
```

- [ ] **Step 2: Run to verify fail**

Expected: FAIL — current `self_heal.py` attaches a FileHandler at module load.

- [ ] **Step 3: Refactor**

Grep: `grep -n "_audit_logger\|FileHandler\|self-heal.log" agent_builder/tools/self_heal.py`. Replace the module-level logger setup with a lazy factory:

```python
# Remove the module-level FileHandler addHandler() call.
_audit_logger = logging.getLogger("agent_builder.self_heal.audit")


def _get_audit_logger() -> logging.Logger:
    """Lazy-init the audit logger. Opens the file handle on first use."""
    if any(hasattr(h, "baseFilename") for h in _audit_logger.handlers):
        return _audit_logger
    log_path = Path(__file__).parent.parent / "self-heal.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _audit_logger.addHandler(handler)
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False
    return _audit_logger
```

Replace every `_audit_logger.info(...)` call inside the module with `_get_audit_logger().info(...)`.

- [ ] **Step 4: Run full test suite**

Run: `pytest`
Expected: all passing — sandbox test that monkeypatches the logger should still work because it patches the module attribute, not the factory function.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/self_heal.py tests/test_self_heal.py
git commit -m "refactor(self_heal): lazy FileHandler — no handle leak at import"
```

---

## Task R3: `_cli_sweep` single-pass

`sweep_artifacts` is called twice — once for the dry-run preview, again for the delete pass. Single filesystem scan + list reuse is simpler.

**Files:**
- Modify: `agent_builder/builder.py` (`_cli_sweep` function)
- Modify: `agent_builder/cleanup.py` (if `sweep_artifacts` needs a return-list mode)

- [ ] **Step 1: Check current sweep_artifacts signature**

Grep: `grep -n "def sweep_artifacts\|_cli_sweep" agent_builder/`. Confirm whether `sweep_artifacts` returns the list of files it would touch, or just acts on them.

- [ ] **Step 2: If needed, make sweep_artifacts return-only-or-act**

If current behaviour is "return list and also delete if not dry_run", no change needed — just capture the list.
If current behaviour is "act, return count", add a `dry_run: bool = False` param that returns the list without acting, and a second call path that deletes from the supplied list.

- [ ] **Step 3: Rewrite _cli_sweep**

```python
def _cli_sweep(args) -> int:
    artifacts = sweep_artifacts(older_than_days=args.older_than, dry_run=True)
    if not artifacts:
        print("Nothing to clean.")
        return 0
    _print_sweep_preview(artifacts)
    if not args.yes and not _confirm("Delete these? [y/N] "):
        return 0
    deleted = sweep_artifacts(artifacts=artifacts, dry_run=False)
    print(f"Deleted {deleted} items.")
    return 0
```

(Exact code depends on existing sweep_artifacts signature. Adjust.)

- [ ] **Step 4: Run existing sweep tests**

Expected: unchanged — sweep semantics identical, just fewer filesystem walks.

- [ ] **Step 5: Commit**

```bash
git add agent_builder/builder.py agent_builder/cleanup.py
git commit -m "refactor(sweep): single filesystem scan instead of two"
```

---

## Task R4: Rollback tool — AGENT.md mention + drop the breadcrumb TODO

`agent_builder/tools/rollback.py` lines 26-28 have a TODO noting the agent's AGENT.md should mention the rollback tool. Do it.

**Files:**
- Modify: `agent_builder/identity/AGENT.md`
- Modify: `agent_builder/tools/rollback.py` (delete TODO)

- [ ] **Step 1: Add rollback section to AGENT.md**

Check if AGENT.md already has a "Rolling back an edit" section (the repo's CLAUDE.md does). If not, add one:

```markdown
## Rolling back an edit

`edit_agent` and `propose_self_change` both write `.bak-<timestamp>` files next to anything they overwrite. To inspect or undo:
1. Call `rollback` with `action="list"` and `target_path="<relative path>"` — see every backup, newest first.
2. Call `rollback` with `action="restore"`, `target_path="..."`, `backup_name="<file>.bak-<stamp>"` — restores the backup. Current state is itself backed up first, so restore is reversible.

Always show the user the `list` output and confirm which backup before calling `restore`.
```

- [ ] **Step 2: Delete the TODO**

In `agent_builder/tools/rollback.py`, remove lines 26–28:

```python
TODO: AGENT.md should mention this tool — a separate agent is editing
AGENT.md in parallel, so this docstring leaves a breadcrumb rather than
touching that file directly.
```

- [ ] **Step 3: Verify CLAUDE.md rebuild still works**

Run: `python -c "from agent_builder.utils import build_claude_md; build_claude_md()"`
Expected: no error.

- [ ] **Step 4: Commit**

```bash
git add agent_builder/identity/AGENT.md agent_builder/tools/rollback.py
git commit -m "docs(builder): document rollback tool in AGENT.md; drop breadcrumb TODO"
```

---

## Task R5: Consolidate path validators into `agent_builder/paths.py`

Four near-identical validators today with subtle divergences: `scaffold._validate_agent_name`, `remove_agent` inline, `rollback._validate_target`, `self_heal._validate_target`. v0.9 and v0.10 will add more. Consolidate before they multiply.

**Files:**
- Create: `agent_builder/paths.py`
- Create: `tests/test_paths.py`
- Modify: `agent_builder/tools/scaffold.py` (use shared validator)
- Modify: `agent_builder/tools/remove_agent.py` (use shared validator)
- Modify: `agent_builder/tools/rollback.py` (use shared validator)
- Modify: `agent_builder/tools/self_heal.py` (use shared validator)

- [ ] **Step 1: Write failing test for the new module**

Create `tests/test_paths.py`:

```python
"""Tests for the shared path validator."""

from pathlib import Path

import pytest

from agent_builder.paths import validate_relative_to_base


def test_relative_inside_base_ok(tmp_path):
    base = tmp_path
    (base / "sub").mkdir()
    resolved, err = validate_relative_to_base("sub", [base])
    assert err is None
    assert resolved == (base / "sub").resolve()


def test_parent_escape_rejected(tmp_path):
    base = tmp_path
    _, err = validate_relative_to_base("../outside", [base])
    assert err is not None
    assert "outside" in err.lower() or "traversal" in err.lower()


def test_absolute_path_outside_rejected(tmp_path):
    base = tmp_path
    _, err = validate_relative_to_base("/tmp/elsewhere", [base])
    assert err is not None


def test_multiple_allowed_bases(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    resolved, err = validate_relative_to_base(str(b / "inside"), [a, b])
    assert err is None


def test_null_bytes_rejected(tmp_path):
    _, err = validate_relative_to_base("foo\x00bar", [tmp_path])
    assert err is not None
```

- [ ] **Step 2: Implement paths.py**

```python
"""Shared path-containment validator for builder tools."""

from pathlib import Path
from typing import Iterable


def validate_relative_to_base(
    path: str,
    allowed_bases: Iterable[Path],
    *,
    allow_drive_letter: bool = False,
) -> tuple[Path | None, str | None]:
    """Resolve `path` and confirm it's under one of `allowed_bases`.

    Returns (resolved, None) on success, (None, error_message) on failure.
    Rejects: null bytes, paths that resolve outside every allowed base.
    Does NOT check existence — callers decide that.
    """
    if "\x00" in path:
        return None, f"path '{path}' contains null byte"

    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError) as e:
        return None, f"path '{path}' cannot be resolved: {e}"

    for base in allowed_bases:
        base_resolved = Path(base).resolve()
        try:
            resolved.relative_to(base_resolved)
            return resolved, None
        except ValueError:
            continue

    bases_str = ", ".join(str(Path(b).resolve()) for b in allowed_bases)
    return None, f"path '{path}' is outside allowed bases [{bases_str}]"
```

- [ ] **Step 3: Run tests**

Expected: pass.

- [ ] **Step 4: Migrate scaffold**

In `agent_builder/tools/scaffold.py`, replace the body of `_validate_agent_name` with a call to the shared validator:

```python
from agent_builder.paths import validate_relative_to_base


def _validate_agent_name(agent_name: str, output_base: str) -> str | None:
    if not NAME_PATTERN.match(agent_name):
        return f"Invalid agent name '{agent_name}'. Must match ^[a-z0-9][a-z0-9-]*$ ..."
    if ".." in agent_name or "/" in agent_name or "\\" in agent_name:
        return f"Invalid agent name '{agent_name}'. Must not contain '..', '/', or '\\\\'."
    _, err = validate_relative_to_base(
        str(Path(output_base) / agent_name),
        [Path(output_base)],
    )
    return err
```

Keep the name-regex check here — it's a slug rule, not a path rule.

- [ ] **Step 5: Migrate remove_agent, rollback, self_heal**

Same pattern in each. The inline validation code shrinks to: slug-regex check (if applicable), then `validate_relative_to_base`. `self_heal` keeps its whitelist + deny-list on top — those are separate concerns.

- [ ] **Step 6: Run full test suite**

Run: `pytest`
Expected: all passing — existing per-tool path tests should still cover the semantics.

- [ ] **Step 7: Commit**

```bash
git add agent_builder/paths.py tests/test_paths.py agent_builder/tools/{scaffold,remove_agent,rollback,self_heal}.py
git commit -m "refactor(paths): consolidate four validators into agent_builder/paths.py"
```

---

## Task R6: Dedupe `Spinner` / `format_tool_call` / `build_claude_md`

Three copies today (`agent_builder/utils.py`, `templates/agent_main.py.tmpl`, and — after v0.9 Phase 0 — `templates/agent_poll.py.tmpl`). Drift observed across all three in past audits. Time to collapse.

**Cost of fix:** generated agents gain a runtime dep on `agent_builder`. Running `python output/<name>/agent.py` now requires `pip install -e .` of the builder package. This is documented as onboarding friction.

**Benefit:** single source of truth. Every spinner/cost/token update lands once and propagates.

**Files:**
- Modify: `agent_builder/utils.py` (exports Spinner / format_tool_call / build_claude_md if not already; verify)
- Modify: `agent_builder/templates/agent_main.py.tmpl` (import, don't inline)
- Modify: `agent_builder/templates/agent_poll.py.tmpl` (import, don't inline — assumes v0.9 Phase 0 has shipped this template)
- Modify: `README.md` — document the install dependency for generated agents
- Modify: `CLAUDE.md` — note the new contract

- [ ] **Step 1: Verify agent_builder.utils exports are stable**

Check:

```bash
python -c "from agent_builder.utils import Spinner, format_tool_call, build_claude_md; print('OK')"
```

Expected: OK. If any is missing from `utils.py` (e.g. only inline in the template currently), move it to `utils.py` first and export.

- [ ] **Step 2: Make build_claude_md AGENT_DIR-parameterisable**

Currently `build_claude_md` in utils.py uses the builder's own `AGENT_DIR`. Generated agents use their own dir. Change signature to accept optional `agent_dir: Path | None = None`, defaulting to the builder's dir when unset:

```python
# In agent_builder/utils.py:
def build_claude_md(verbose: bool = False, agent_dir: Path | None = None) -> None:
    agent_dir = Path(agent_dir) if agent_dir else Path(__file__).parent
    # ... existing logic, but reads from agent_dir instead of hardcoded path ...
```

Verify existing builder tests still pass.

- [ ] **Step 3: Slim down agent_main.py.tmpl**

Delete the inlined `Spinner` class, `_NullCtx`, `_truncate`, `format_tool_call`, `build_claude_md`, `IDENTITY_FILES`, `CLAUDE_MD_HEADER` from the template. Replace with:

```python
from agent_builder.utils import (
    Spinner,
    format_tool_call,
    build_claude_md,
)
```

Update the `build_claude_md(verbose=verbose)` call in the template's `main()` to `build_claude_md(verbose=verbose, agent_dir=AGENT_DIR)`.

Count the line savings — expect ~200 lines dropped from the template.

- [ ] **Step 4: Same surgery on agent_poll.py.tmpl**

Same imports, same `build_claude_md` call signature. Delete the inlined copies from the poll template.

- [ ] **Step 5: Update REQUIRED_PLACEHOLDERS if needed**

The templates no longer embed the Spinner class inline but still have all the same `{{...}}` placeholders. No change needed to `REQUIRED_PLACEHOLDERS_BY_MODE` — only the body shrunk, not the placeholder set.

- [ ] **Step 6: Test — generated agent still works**

Scaffold a throwaway agent in a test env, run it, confirm:
- Spinner displays
- Tool-call preview formats identically
- `CLAUDE.md` regenerates from identity files
- No `ImportError: No module named 'agent_builder'`

Add an integration test in `tests/test_template_imports.py`:

```python
def test_generated_agent_imports_from_agent_builder(tmp_path):
    import asyncio
    from agent_builder.tools.scaffold import scaffold_agent
    out = tmp_path / "output"
    out.mkdir()
    asyncio.run(scaffold_agent({"agent_name": "t", "description": "x"}, output_base=str(out)))
    agent_py = (out / "t" / "agent.py").read_text()
    assert "from agent_builder.utils import" in agent_py
    assert "class Spinner" not in agent_py
    # AST-parse the generated file to confirm it's valid Python
    import ast
    ast.parse(agent_py)
```

- [ ] **Step 7: README note**

Add to README.md "Running a generated agent" section:

```markdown
Generated agents depend on the `agent_builder` package at runtime for shared utilities (`Spinner`, `format_tool_call`, `build_claude_md`). If you move a generated agent outside the repo, install the builder package in the same environment:

    pip install -e /path/to/claude-agent-sdk-playground

Inside the repo, the editable install from `pip install -e .` already covers this.
```

- [ ] **Step 8: CLAUDE.md note**

Under "Generated-agent contract", add:

```markdown
Generated agents import `Spinner`, `format_tool_call`, and `build_claude_md` from `agent_builder.utils`. Running a generated agent requires `agent_builder` to be installed in the same Python environment. The editable install from `pip install -e ".[dev]"` covers this.
```

- [ ] **Step 9: Run full test suite**

Run: `pytest`
Expected: all passing. Any template-fixture tests that compared the template file byte-for-byte will need updates — expected.

- [ ] **Step 10: Commit**

```bash
git add agent_builder/utils.py agent_builder/templates/ README.md CLAUDE.md tests/test_template_imports.py
git commit -m "refactor(utils): dedupe Spinner/format_tool_call/build_claude_md across templates"
```

---

## Self-Review

**Coverage vs v0.8 plan:**
- 1.1 (`AGENT_TEST_MODE`) — covered by v0.9 composition retrofit Task 0.2. Not duplicated here.
- 1.2 (gate web tools) — R1.
- 1.3 (consolidate path validators) — R5.
- 1.4 (lazy self-heal FileHandler) — R2.
- 2.1 (dedupe Spinner / format_tool_call / build_claude_md) — R6.
- 2.3 (`_cli_sweep` single-pass) — R3.
- Rollback TODO breadcrumb — R4.

**Deliberately excluded:** 2.2 (complexity refactors — separate PR, not blocking), 3.1 (`python -m build` smoke), 3.2 (`make setup`) — all roll forward to their own release-plumbing round.

**Ordering guidance for executor:**
1. R6 (utils dedupe) — lands between v0.9 Phase 0 and Phase A so the new poll template gets the deduped imports from day one rather than being retrofitted.
2. R5 (path validators) — lands before Phase B so new tools use the shared validator natively.
3. R1, R2, R3, R4 — anytime during v0.9 execution; each is a self-contained commit.

**No placeholders in plan:** every step has exact code or a pinpointed file edit. One prose-level step (R3 Step 2 — "If needed, make sweep_artifacts return-only-or-act") is contingent on the current signature; the executor checks with `grep` first and adjusts.
