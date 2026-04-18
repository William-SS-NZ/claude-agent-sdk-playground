# v0.8.0 release plan

Sequenced plan for the next release. Items pulled from `audit.md` "Prioritized fix list" rows marked *no (v0.8.0)* plus `TODO.md` high-priority deferrals. Target: ship a PyPI-ready public build.

Written 2026-04-19, post-audit. Post-[Unreleased] fixes already on `main` are listed in `CHANGELOG.md`; this file covers what lands next.

---

## Scope

Three themes, in priority order:

1. **Safety & correctness** — close the last audit gaps that could bite a public user.
2. **Code health** — dedup, consolidate, reduce drift surface.
3. **Release mechanics** — PyPI smoke-test, onboarding script.

Non-goals for v0.8.0: template variants, registry migration tooling, self-heal unified-diff UI. Those are in `TODO.md#Polish` and wait on user demand.

---

## Phase 1 — safety & correctness

### 1.1 Replace `_set_test_mode` file mutation with an env var (audit 1.4 / B4)

**Why now:** the current approach mutates `tools.py` on disk and relies on a `finally` block to restore. A killed interpreter leaves `TEST_MODE = True` stuck; subsequent real runs silently return mock data. This is the last known footgun in the testing path.

**Change:**

- `write_tools.TOOLS_HEADER`: replace `TEST_MODE = False` line with `TEST_MODE = os.environ.get("AGENT_TEST_MODE") == "1"` and `import os`.
- `test_agent._set_test_mode`: delete. Instead wrap the `query()` call in `with _patched_env("AGENT_TEST_MODE", "1"):` (context manager that sets and restores).
- `_load_tools_server`: no change needed — it reimports the module each call, picking up the env var at import time.
- **Backwards compat:** existing generated agents still work (they'll keep using the old header with `TEST_MODE = False`). On first `edit_agent` that rewrites `tools.py` they'll get the new header.

**Tests:** kill-mid-run simulation (spawn subprocess, `SIGKILL`, assert no stale mode). Also an existing-agent test to confirm the header swap is safe when regenerated.

**Risk:** low. Env-var leaking across test runs in the same process — guard with context manager, unit test a nested scenario.

**Effort:** M (half-day including the test matrix).

### 1.2 Gate `WebFetch` / `WebSearch` (audit 6.1 / F3)

**Why now:** public users pasting URLs in discovery can trigger outbound fetches with no allow-list. Pre-publish decision point.

**Options evaluated:**

- A. Off by default, `ENABLE_WEB_TOOLS=1` to opt in. Simplest. Preferred.
- B. Domain allow-list + prompt-on-unknown. More code. Not worth it for a v0.8.0.
- C. Keep on (status quo). Risk not worth taking before PyPI.

**Change (option A):**

- `builder._build_options`: conditionally add `WebFetch` / `WebSearch` to `allowed_tools` based on env var.
- `AGENT.md` Phase 2: note web tools may be off; if the user needs them for design research, set the env var.
- README: document the env var in a dedicated subsection.

**Tests:** `test_builder_cli` covers `_build_options` — add one case for each env-var state.

**Effort:** S.

### 1.3 Consolidate path validators (audit 3.1 / 6.4)

**Why now:** four validators with subtle divergences. A future edit to one will drift. Also touches the surface of every path-related bug we might find post-release.

**Change:**

- New `agent_builder/paths.py`:

```python
def validate_relative_to_base(
    path: str,
    allowed_bases: Iterable[Path],
    *,
    allow_drive_letter: bool = False,
) -> tuple[Path | None, str | None]:
    """Resolve `path` and confirm it lands under one of `allowed_bases`.
    Returns (resolved_or_None, error_or_None)."""
```

- `scaffold._validate_agent_name` → calls it with `[Path(output_base)]` plus keeps the name-regex check.
- `remove_agent` → calls it directly.
- `rollback._validate_target` → calls it with `[REPO_ROOT, BUILDER_DIR, OUTPUT_DIR]`.
- `self_heal._validate_target` → calls it with `[BUILDER_DIR]` plus the whitelist + deny-list on top.

**Tests:** existing per-tool path tests cover this. Add a dedicated `tests/test_paths.py` for the shared validator (symlinks, drive letters, UNC paths, `..` escape).

**Effort:** M.

### 1.4 Lazy `self-heal.log` FileHandler (audit 3.4)

**Why now:** current module-level `FileHandler` opens the real log file at import time — tests leak handles and pollute the real `agent_builder/self-heal.log` with test noise.

**Change:**

- Move `_audit_logger` setup into a module-level factory `_get_audit_logger()` called from `propose_self_change()`. First call opens the handler; subsequent calls reuse.

**Tests:** existing sandbox test already monkeypatches the logger — it'll keep working. Add a "import self_heal; assert no handler attached" test.

**Effort:** XS.

---

## Phase 2 — code health

### 2.1 Dedupe Spinner / format_tool_call / build_claude_md (audit 2.1)

**Why now:** three copies, observed drift in `format_tool_call` fallback keys, frame-index math, `_truncate` defaults. Every new spinner feature (token readout, cost estimate) has shipped twice and risks divergence again.

**Change:**

- Generated agents gain a runtime dep on `agent_builder`. Template rewrites:

```python
from agent_builder.utils import Spinner, format_tool_call, build_claude_md
```

- `build_claude_md` gains an `AGENT_DIR`-aware call signature that generated agents use (already matches for the builder).
- `pyproject.toml`: expose `agent_builder` for installed use (no new dep; the generated agent's `requirements` / install picks it up).
- **Onboarding impact:** running `python output/<name>/agent.py` requires `pip install -e .` of the builder package. Document this in README under "Generated agents".

**Tests:** existing template `build_claude_md` tests collapse to unit tests on `agent_builder.utils` (drop the template fixture — it's the same code). Existing cli_mode wiring tests still work against the shorter template.

**Risk:** medium. Packaging the builder for use inside generated agents is a distribution concern — verify `pip install -e .` on a clean env also makes `agent_builder` importable from `output/<name>/agent.py`.

**Effort:** L. Own PR.

### 2.2 Complexity refactors (audit 4.1–4.3)

Split in separate commits in the same PR:

- `builder.py::_run_one_query` → `_handle_assistant / _handle_result / _handle_system` + main dispatcher.
- `scaffold.py::scaffold_agent` → `_render_template / _assemble_template_context / scaffold_agent` orchestrator.
- `test_agent.py::test_agent` → `_prepare_for_test / _build_test_options / _summarise_results / test_agent` orchestrator.

No behavior change. Pure refactor. Tests must pass unchanged.

**Effort:** M.

### 2.3 `_cli_sweep` single-pass (audit 3.5)

Capture the dry-run file list and reuse it for the delete pass. One filesystem scan instead of two.

**Change:** `sweep_artifacts` already returns the list. `_cli_sweep` prints + deletes from the returned list rather than calling `sweep_artifacts` twice.

**Effort:** XS.

---

## Phase 3 — release mechanics

### 3.1 `python -m build` smoke test (TODO.md, was deferred from v0.7.0)

Verify:

- Source + wheel build with no deprecation warnings.
- `PolyForm-Noncommercial-1.0.0` license classifier passes modern setuptools validation (or switch to SPDX expression syntax if it doesn't).
- Generated sdist / wheel are installable in a fresh venv and `python -m agent_builder.builder --doctor` returns 0.

**CI:** add `python -m build && twine check dist/*` to GitHub Actions alongside pytest.

**Effort:** S; blocker for any PyPI publish.

### 3.2 `make setup` onboarding

**Target flow:**

```bash
git clone <repo>
cd claude-agent-sdk-playground
make setup   # editable install, dev extras, pre-commit hooks, initial pytest
```

**Change:** single-file Makefile (or equivalent `scripts/setup.sh` for Windows users — `make` isn't universal). Either works; pick one.

**Effort:** S.

### 3.3 Release checklist

Before tagging v0.8.0:

- [ ] All phase-1 items merged, tests green.
- [ ] `--doctor` exits 0 on a fresh clone.
- [ ] `python -m build` + `twine check dist/*` pass.
- [ ] README screenshots / examples reflect new `ENABLE_WEB_TOOLS` guidance.
- [ ] CHANGELOG closes `[Unreleased]` section and opens `[0.8.0]` with the release date.
- [ ] `pyproject.toml` version bumped to `0.8.0`.
- [ ] Git tag `v0.8.0`, release notes pulled from CHANGELOG.

---

## Out of scope for v0.8.0

Kept in `TODO.md#Polish` for later:

- Registry migration on startup.
- Bulk edit from a markdown spec file.
- Self-heal unified-diff UI.
- `--show-self-heals` CLI.
- Builder's own `MEMORY.md` self-update.
- Rollback batch mode.
- Template variants (minimal/full/iterative).

## Order of operations

Suggested PR sequence (each self-contained, green-tests-only):

1. **PR-1** (small) — 1.2 + 1.4 + 2.3. Fast wins, low risk.
2. **PR-2** (medium) — 1.3 path consolidation. Touches many files but tests don't change semantically.
3. **PR-3** (medium) — 1.1 TEST_MODE env var. Coordinated header + test_agent change.
4. **PR-4** (large) — 2.1 dedup. Biggest diff, biggest payoff. Merge last before release.
5. **PR-5** (medium) — 2.2 complexity refactors. Pure cleanup once the surface is settled.
6. **PR-6** (small) — 3.1 + 3.2 release plumbing. Ship with the release tag.

Rough calendar: phase 1 in week 1, phase 2 in week 2, phase 3 in week 3. Tag v0.8.0 at end of week 3 if CI is green on all three.
