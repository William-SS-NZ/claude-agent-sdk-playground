# double-check.md

Things an external expert should verify before relying on this repo in production. Items here are ones that are security-sensitive, data-destructive, cost-sensitive, or held together by trust in the LLM rather than by code. Test coverage for each is noted but tests only catch what they test for.

Covers v0.7.0 (180 passing tests, 9 builder tools, 9 CLI subcommands).

**2026-04-19 audit update:** items marked **✅ CLOSED** below were resolved in the post-audit fix round — see `audit.md` and `CHANGELOG.md` Unreleased section. Items marked **→ v0.8.0** are sequenced in `docs/next-release-plan.md`.

---

## A. Security-sensitive

### A1. Path-traversal guards on every tool that touches the filesystem

Four tools resolve user-controlled agent names or target paths into filesystem paths:

| Tool | Guard location | What it protects |
|------|----------------|------------------|
| `scaffold_agent` | `scaffold.py::_validate_agent_name` (regex `^[a-z0-9][a-z0-9-]*$` + `..` check + resolved-prefix check) | Output dir creation |
| `remove_agent` | `remove_agent.py` (reuses `_validate_agent_name` + `target.relative_to(base)` check) | `shutil.rmtree` deletion |
| `edit_agent` | `edit_agent.py` (reuses `_validate_agent_name`) | File writes to existing agent |
| `self_heal.propose_self_change` | `self_heal.py::_validate_target` (explicit absolute/drive-letter reject + `resolved.relative_to(BUILDER_DIR)` + deny-list + whitelist) | **Edits the builder's own code** |
| `rollback` | `rollback.py` (custom validator — allows repo root / `agent_builder/` / `output/`; backup_name must match basename; strict `\d{8}-\d{6}` stamp regex) | File writes + backup restore |

**Ask the expert to verify:**
- No way to escape via symlinks, UNC paths (`\\server\share\...`), NTFS alternate data streams, or mixed-case Windows drive letters.
- `Path.resolve()` behaviour under symlinks on every OS the repo runs on.
- `relative_to(base)` after `.resolve()` on Windows junctions.
- `backup_name` in `rollback` is regex-checked; confirm the regex can't match a path-traversal via `..` smuggled into a valid-looking stamp.

### A2. `safety_hook` in generated agents

`agent_builder/templates/agent_main.py.tmpl` registers a `PreToolUse` hook on `Bash`, `Write`, `Edit`. Two parts:

- `_BLOCKED_BASH_PATTERNS` — substring match on command text. Easy to bypass with `rm  -rf /` (double space), `r\m -rf /`, env-var indirection (`X=rm; $X -rf /`), base64 pipe, etc.
- `_SENSITIVE_PATH_MARKERS` — substring match on `file_path`, both slash styles, case-insensitive. Could miss NTFS short names (`PROGRA~1`), UNC paths, or newly-invented sensitive paths not in the list.

**Ask the expert to verify:**
- Whether this level of protection is the right bar for an "acceptEdits" agent, or if we should escalate to a proper allow-list / AST-based shell check.
- List completeness — are there sensitive paths we're missing on Linux (`/etc/shadow`, `~/.aws/credentials`), macOS (`~/.config`, Keychain paths), Windows (`%APPDATA%\Microsoft\Credentials`, `NTUSER.DAT`)?
- Whether the fork-bomb signature `:(){ :|:& };:` is the right canary when any one-liner with `&` can achieve the same effect.

### A3. `propose_self_change` confirmation gate

This is the **only** barrier between the LLM and self-modification of the builder's own code / identity / template. Implementation: synchronous `input("  Apply this change? [y/N]: ")` called via `asyncio.to_thread`. Only `y` / `yes` proceeds.

**Ask the expert to verify:**
- `input()` actually blocks the event loop sufficiently that the LLM can't bypass via parallel tool calls.
- No path where the confirmation is skipped (search for `_prompt_confirm` callers).
- Audit log (`agent_builder/self-heal.log`) writes are durable — no race where the proposal gets applied but the log write fails.
- `.bak-<timestamp>` backup is written BEFORE the overwrite, not after.

### A4. AGENT.md-enforced rules that the model can ignore

These are instructions in markdown, not code. The LLM is told to follow them; nothing stops it from violating:

- Phase 1: "ask for name and wait for reply"
- Phase 4: "STOP on any `is_error`"
- Phase 5: "always run `test_agent`, even for empty-tools agents"
- Self-heal: "only after immediate task is handled", "only on observed failures", "never retry a declined proposal"
- Removing agents: "ask for explicit confirmation before deleting"

**Ask the expert to verify:**
- Where these should be enforced in code vs markdown. `registry add` enforcing Phase 4 completeness (v0.5.1) is the only existing hard gate. Candidates for similar: Phase 5 (block `registry add` until `test_agent` run?), Phase 1 name-ask (no easy way — it's pure conversation).
- Whether the model actually follows these rules across different temperatures / context-window states in practice.

---

## B. Data-loss risk

### B1. `remove_agent` + `--purge-all` are unrecoverable

`output/<name>/` is gitignored. `shutil.rmtree` removes the directory. `.bak` files inside are also gone. Registry JSON is the only record, and `--purge-all --yes` wipes that too.

**Ask the expert to verify:**
- Whether a `--trash` / "move to ~/.agent_builder_trash" mode would be worth adding for recoverability.
- The confirmation prompt wording makes the irreversibility obvious.

### B2. `--sweep` `--older-than` logic

`cleanup.py::sweep_artifacts`:
- `.bak-*` files: deletes if mtime older than cutoff.
- Per-run logs: deletes if mtime older than cutoff.
- `screenshots/`: wholesale delete **only if every file inside is older than cutoff** — protects a recent screenshot sitting in an otherwise-stale dir.

**Ask the expert to verify:**
- mtime vs ctime on Windows — we use mtime; could a backup restore or a touch reset the clock unexpectedly?
- The `screenshots/` all-or-nothing logic — is it too conservative (stale dir with one accidentally-touched file never cleaned) or too aggressive (expert might want to preserve any non-empty dir)?

### B3. `edit_agent` / `self_heal` / `rollback` backups — ✅ CLOSED

Every overwrite writes `<file>.bak-<YYYYMMDD-HHMMSS>`. Sub-second repeat operations can collide (only rollback explicitly aborts on collision; the other two silently overwrite the backup, **losing the original**).

**Ask the expert to verify:**
- Whether edit_agent and propose_self_change should also abort on `.bak-<stamp>` collision.
- Whether a monotonic counter suffix would be safer (`.bak-20260419-153045-0001.md`).

### B4. `test_agent` mutates `tools.py` in place — → v0.8.0

To switch on TEST_MODE, `test_agent` does a string replace `TEST_MODE = False` → `TEST_MODE = True` in the target's `tools.py`, runs, then restores in `finally`. Two failure modes:

1. Python interpreter killed between flip and finally → `TEST_MODE = True` sticks, all subsequent real runs silently return mock data.
2. Two `test_agent` runs against the same agent concurrently → file race, unpredictable end state.

Finally-block coverage is tested (`tests/test_test_agent_test_mode.py`) but kill-mid-run isn't.

**Ask the expert to verify:**
- Acceptable risk level vs the alternative of threading TEST_MODE via an env var at import time (avoids file mutation entirely).

---

## C. Cost-sensitive

### C1. Budget caps rely on the SDK honouring `max_budget_usd`

Builder ships with `max_budget_usd=5.00`, `max_turns=50`. Generated agents default to `max_budget_usd=1.00`, `max_turns=25` (configurable per-agent via scaffold params).

**Ask the expert to verify:**
- The SDK actually enforces `max_budget_usd` — I've relied on this without reading the SDK source. If it's advisory or measured after-the-fact, runaway costs are possible.
- Per-call costs: `WebFetch` / `WebSearch` have no per-call cap (they fall inside the overall budget). Whether this is sufficient or we need a rate limit.

### C2. `test_agent` makes real SDK calls

Per-prompt cost unpredictable (depends on tool chain the LLM invokes). AGENT.md warns the user it takes 1-3 min per prompt, but doesn't cap cost beyond the generated agent's own `max_budget_usd`.

**Ask the expert to verify:**
- Whether to add a hard-coded budget cap on test_agent runs (e.g. `max_budget_usd=0.50` per prompt) independent of the agent's own settings.

### C3. Live cost display is estimated, not authoritative

`Spinner._estimated_cost` uses hardcoded Opus 4.x pricing (`$15/MT input, $75/MT output`). The tilde-prefixed display (`~$0.12`) is an estimate until `ResultMessage.total_cost_usd` arrives.

**Ask the expert to verify:**
- Pricing is current as of your review date.
- Behaviour when the SDK is configured to use Sonnet or Haiku — estimate will over-report.

---

## D. Correctness-critical

### D1. `_count_custom_tools_from_source` AST walk

`test_agent.py::_count_custom_tools_from_source` parses `tools.py` and counts the `tools=[...]` kwarg of `create_sdk_mcp_server(...)`. Used to decide whether to relax the "must call custom tool" test criterion.

Fail-soft: any parse error or missing call returns 0 ("no tools"). That relaxes the test, which is the LENIENT direction — a genuine multi-tool agent misclassified as no-tools would have its tests pass instead of fail.

**Ask the expert to verify:**
- Whether fail-soft is the right direction here, or we should fail-loud (error out test_agent if we can't determine tool count).

### D2. Template placeholder drift — ✅ CLOSED (doctor + scaffold now share one `REQUIRED_PLACEHOLDERS` tuple)

Scaffold has two guards:

1. Pre-substitution: every expected placeholder (`_REQUIRED_PLACEHOLDERS`) must exist in the template.
2. Post-substitution: no `{{...}}` may survive.

**Ask the expert to verify:**
- Completeness of `_REQUIRED_PLACEHOLDERS` — it must include every placeholder scaffold fills. Missing one wouldn't trigger either guard. Grep the template for `\{\{[^}]+\}\}` and diff against `_REQUIRED_PLACEHOLDERS`.

### D3. `build_claude_md` drift

Two copies: one in `agent_builder/utils.py` (used by the builder), one inlined into `agent_main.py.tmpl` (used by every generated agent). Drifted once before — the template version silently skipped missing required files while the utils version raised. Both are now covered by tests against the same scenarios.

**Ask the expert to verify:**
- The two implementations still produce byte-identical output for the same inputs.
- Whether deduping (generated agents import from `agent_builder.utils`?) is worth the packaging complexity.

### D4. Registry completeness check lives in `registry add`

`registry.py::_verify_agent_complete` checks `output/<name>/` has all of `agent.py`, `tools.py`, `AGENT.md`, `SOUL.md`, `MEMORY.md`. If the check misses a file that's required at runtime, incomplete builds still register.

**Ask the expert to verify:**
- `REQUIRED_AGENT_FILES` is comprehensive — what does the template actually import at agent startup?

---

## E. Drift / staleness

### E1. CLAUDE.md at root is hand-maintained

Unlike per-agent CLAUDE.md (auto-generated from identity files), the root `CLAUDE.md` is written by hand to guide Claude Code sessions. Easy to let it get stale.

**Ask the expert to verify:**
- Whether we should auto-generate it from code inspection instead (list tools from `tools/__init__.py`, commands from `builder.py` argparse).

### E2. CHANGELOG drift

Humans write it. Easy to miss entries.

### E3. `double-check.md` (this file) drift

Written at v0.7.0. If the code changes, this file will not. Flag stale items on re-review.

---

## F. Things I'd especially like a second opinion on

1. **Self-heal is the scariest feature.** The builder can modify its own code. The only gate is a stdin prompt. Is this the right trade-off, or should self-heal write a PR / diff file for human review instead of applying inline?
2. **`acceptEdits` permission mode on the builder** means the LLM can Edit/Write files without asking, across the whole project. The safety_hook for generated agents doesn't apply to the builder's own runs — the builder has broader powers than anything it builds. Intentional, but worth flagging.
3. **`WebFetch` / `WebSearch` are on by default** (v0.5.3). User prompts containing URLs could trigger unexpected fetches. No URL allow-list. — → v0.8.0 (`ENABLE_WEB_TOOLS` env-var gate).
4. **TEST_MODE file mutation** is a smell. A proper fix would pass TEST_MODE via env var or constructor arg. Current approach works because of defensive finally, but could be cleaner. — → v0.8.0 (env-var rewrite planned in `docs/next-release-plan.md#1.1`).
5. **`propose_self_change` can't be used to disable itself** — the tool's own source is under `agent_builder/tools/`, which is in the whitelist. Worth tightening the scope to forbid editing `self_heal.py` specifically. — ✅ CLOSED (added to `DENY_FILES`, regression test in place).

---

## G. Tests that exist vs gaps

| Area | Coverage | Gap |
|------|----------|-----|
| Path traversal | `test_scaffold`, `test_remove_agent`, `test_self_heal`, `test_rollback` — heavy coverage | No test for UNC paths or NTFS junctions on Windows |
| Registry validation | `test_registry` (11 tests) — seeding/old-shape/dedup/remove/describe/SDK-config-preserve | No test for concurrent `add` calls |
| Budget enforcement | None | Relies on SDK; no assertion we actually stop at `max_budget_usd` |
| `safety_hook` | None in Python; handled at SDK hook level | No unit tests for the Bash pattern list or sensitive path matcher |
| TEST_MODE restore | `test_test_agent_test_mode` — covers import crash and prompt crash | No test for process-killed-mid-run |
| cli_mode wiring | `test_cli_dispatch_wiring` — 6 AST tests | No end-to-end subprocess test (would require API mock) |
| Spinner + cost | `test_spinner_cost` — token accumulation, cost estimate vs authoritative | No test for thread safety |

---

## Bottom line

If one thing gets reviewed, make it **A3 (`propose_self_change` confirmation gate)**. That's the capability that lets the system modify itself, and the only safeguard is an `input()` call. Everything else is either defense-in-depth or conventional file-write safety.
