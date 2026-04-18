# audit.md

Pre-release code audit of `claude-agent-sdk-playground` (v0.7.0, 2026-04-19).

**Status (2026-04-19, post-audit):** must-ship fixes + quick wins applied — see the "Shipped in [Unreleased]" block in `CHANGELOG.md` and `TODO.md`. Items marked **✅ FIXED** below were closed in that round. Everything else sits in `docs/next-release-plan.md` for v0.8.0. 186/186 tests green.

Scope: every file under `agent_builder/`, the generated-agent template, tests, project metadata, and the `output/ez-read/` real-world sample. Focus: cleanup for public release — bugs, fragile logic, drift, complexity, edge cases.

Severity legend:

- **BUG** — incorrect behavior observable today (or very likely under normal use).
- **DRIFT** — two places that must stay in sync are diverging. Will cause a future bug.
- **FRAGILE** — works today, likely to break under a minor change or an edge case.
- **CLEANUP** — dead code, stale comments, inconsistent style, pre-release polish.
- **COMPLEXITY** — a function/module that is longer or more nested than it needs to be.

---

## 1. Bugs (observable today)

### 1.1 `write_identity` MCP schema omits `user_md` — BUG — ✅ FIXED
**File:** `agent_builder/tools/write_identity.py:72-80`

`FILE_MAP` has `user_md → USER.md`, and `write_identity()` writes it when supplied. But the MCP tool schema advertises only `agent_name, agent_md, soul_md, memory_md`. The LLM cannot pass `user_md` through the tool call — the USER.md code path is unreachable via the SDK. `edit_agent` exposes `user_md` correctly; `write_identity` does not.

**Fix:** add `"user_md": str` to the schema. Trivial.

### 1.2 Doctor's `EXPECTED_TEMPLATE_PLACEHOLDERS` drifted from scaffold's `_REQUIRED_PLACEHOLDERS` — BUG — ✅ FIXED
**Files:** `agent_builder/doctor.py:26-36` vs `agent_builder/tools/scaffold.py:128-140`

Scaffold requires 11 placeholders in the template; doctor checks 9. Missing from doctor:

- `{{builder_version}}`
- `{{cli_help_epilog}}`

Doctor is explicitly the drift guard for template placeholders (per CLAUDE.md and double-check.md D2), but it cannot catch the two placeholders added in v0.6.0 / v0.7.0. Ironic given the stated purpose.

**Fix:** sync the two tuples or move both to a shared constant in one module (e.g. `doctor.py` imports from `scaffold.py`, or vice versa).

### 1.3 Builder AGENT.md advertises a non-existent permission mode — BUG
**File:** `agent_builder/identity/AGENT.md:102`

```
- **Read-only**: tools=["Read", "Glob", "Grep"], permission_mode="dontAsk"
```

Actually `dontAsk` *is* in the SDK's `Literal` enum for `permission_mode` (confirmed by inspecting `ClaudeAgentOptions.__init__`: `'default', 'acceptEdits', 'plan', 'bypassPermissions', 'dontAsk', 'auto'`). So this isn't a hard bug, but the scaffold tool's *docstring* claims only `'default', 'acceptEdits', 'bypassPermissions', 'plan'` are valid (`scaffold.py:215`). That is the mismatch: the docstring is stale relative to the SDK and AGENT.md. Pick one source of truth.

### 1.4 `_set_test_mode` mutates every occurrence of the literal string — BUG / FRAGILE
**File:** `agent_builder/tools/test_agent.py:35-42`

Uses `content.replace("TEST_MODE = False", "TEST_MODE = True")` (and the inverse). Unscoped to module-level assignment. If a user-generated tool happens to embed the literal string `TEST_MODE = False` inside a docstring, comment, or string (e.g. in a help message telling the user what the flag is), that copy gets flipped too. Also flipped back inconsistently if the surrounding whitespace differs.

**Recommended fix:** pass `TEST_MODE` via an env var that `tools.py` reads at import (`TEST_MODE = os.environ.get("AGENT_TEST_MODE") == "1"`). Removes file mutation entirely and closes the "interpreter killed mid-run leaves `TEST_MODE = True`" gap that double-check.md B4 flags.

### 1.5 `_backup` silently clobbers sub-second collisions — BUG — ✅ FIXED
**Files:** `agent_builder/tools/edit_agent.py:63-70`, `agent_builder/tools/self_heal.py:162-167, 189-191`

Both write `target.with_suffix(target.suffix + f".bak-<stamp>")` without checking existence. Two calls within the same second (automated test, self-heal batch) overwrite the first backup. The *original* file is gone — the "backup" preserved is actually the already-modified file.

`rollback.py:230-236` explicitly aborts on collision. The three call sites should behave consistently.

**Fix:** either abort on collision (match `rollback`) or add a monotonic counter (`.bak-<stamp>-0001`).

### 1.6 `format_tool_call` dead-code branch for `test_prompts` — BUG (dead) — ✅ FIXED
**File:** `agent_builder/utils.py:159-160`

```python
if k == "test_prompts" and isinstance(v, list):
    v = f"{len(v)} prompts"
```

This lives inside the `for k in keys` loop. `test_prompts` is never in `keys` — neither the per-tool `previews` map nor the `mcp__` fallback `("action", "agent_name", "url", "prompt")`. Branch is unreachable.

Either add `"test_prompts"` to the `mcp__` fallback list (intent seems to be a nice preview for `test_agent` calls) or delete the dead branch.

### 1.7 `agents.json` schema drift — BUG
**File:** `agent_builder/registry/agents.json`

The single registered agent `ez-read` lacks `updated_at`, `max_turns`, `max_budget_usd`, `permission_mode` — all added in v0.5.0. Registry `describe` tolerates absence (good), but `edit_agent._bump_registry_updated_at` will silently fix it only on next edit. No migration path on startup. Pre-release: either migrate old entries or document the tolerant-read contract in CLAUDE.md.

### 1.8 `_registered_agent_names` tolerant but `registry` add-path is not — BUG (interaction)
**File:** `agent_builder/builder.py:377-385`

If `agents.json` is malformed JSON, `_registered_agent_names` returns `[]` silently (swallows `json.JSONDecodeError`). The same registry then blows up in `registry add` with an un-caught `json.JSONDecodeError` (`registry.py:41` — `json.loads(path.read_text(...))` has no try/except). Inconsistent defensive posture: the CLI helper hides the problem; the core tool crashes.

### 1.9 `IDENTITY_SOFT_LIMIT = 6000` may be stale — BUG / stale
**File:** `agent_builder/tools/write_identity.py:15-19`

Comment says identity content flows through `CreateProcessW`'s 8191-char `lpCommandLine`. But the SDK loads CLAUDE.md from the project dir via `setting_sources=["project"]` — the content sits on disk, not in argv. Unless the SDK serializes identity into CLI args (verify!), the warning is misleading. If verification shows it is no longer a real constraint, remove the warning to stop scaring users.

---

## 2. Drift (two places must stay in sync)

### 2.1 Three copies of the same utility code — DRIFT
Inlined into `templates/agent_main.py.tmpl`, duplicated with hand-reduced versions in `agent_builder/utils.py`, and a third `_truncate` in `test_agent.py`. Already drifted in small ways:

| Feature | `utils.py` | template | `test_agent.py` |
|---|---|---|---|
| `format_tool_call` mcp fallback keys | `("action", "agent_name", "url", "prompt")` | `("url", "query", "action", "prompt", "path")` | n/a |
| `test_prompts` special case | yes (dead, see 1.6) | no | n/a |
| Spinner frame index | `int(elapsed * 10) % len(self.FRAMES)` | `int(elapsed * 10) % 4` hardcoded | n/a |
| `_truncate` default limit | 80 | 80 | 240 |
| `build_claude_md` signature | takes `source_dir/output_dir` | operates on `AGENT_DIR` only | reuses utils version |

Double-check.md D3 already flags this as a known drift risk and mentions it bit the project before. The only durable fix is dedup — generated agents could `from agent_builder.utils import build_claude_md, Spinner, format_tool_call`, at the cost of making generated agents depend on the builder package at runtime. Given the current test effort spent on keeping them in sync (6 tests just for the template's `build_claude_md`), the packaging cost is likely worth it.

### 2.2 `builder.py` and template diverge on response rendering — DRIFT
`builder.py::_run_one_query` logs `subtype / num_turns / duration_ms / denials / errors / tokens` on every `ResultMessage` (lines 196-206). `template::_drain_responses` only logs the error subtype on failure (line 319). A user debugging a generated agent gets markedly less detail in the `.log` file than the builder's own log. Should converge.

### 2.3 `CLAUDE.md` (root) is hand-maintained — DRIFT
Double-check.md E1 calls this out. Concrete drift observed now: root `CLAUDE.md` claims `pytest` has `all 180+` — actual count not verified, README says `42` elsewhere. These go stale fast.

### 2.4 `README.md` claims 6 tools, code has 9 — DRIFT — ✅ FIXED
**File:** `README.md:77` "The 6 builder tools (MCP server)". Actual count per `tools/__init__.py`: 9 (adds `remove_agent`, `propose_self_change`, `edit_agent`, `rollback`). The README list on lines 79-86 omits them entirely.

### 2.5 `README.md` mentions "all 42 tests as of v0.2.0" — DRIFT — ✅ FIXED
**File:** `README.md:142`. Project is v0.7.0 now. Either update the number or drop the count and say "run `pytest`".

### 2.6 `agent_builder/CLAUDE.md` checked in but is auto-generated — DRIFT — ⚠️ NOT AN ISSUE
(Verified 2026-04-19 post-audit: `git ls-files` confirms only root `CLAUDE.md` is tracked. `agent_builder/CLAUDE.md`, `self-heal.log`, and `.egg-info/` are gitignored AND untracked. Original audit claim was wrong.)

**File:** `agent_builder/CLAUDE.md` (8407 bytes)

`.gitignore:40` lists `agent_builder/CLAUDE.md`. But the file is on disk and was included in the snapshot context. It's the rebuilt-on-startup artifact — shouldn't be in git. Either it was committed before the ignore rule landed, or the ignore rule is inactive in the tracked tree. Run `git rm --cached agent_builder/CLAUDE.md` and re-commit.

Same question for `output/ez-read/CLAUDE.md`. `scaffold.py::GITIGNORE_CONTENT` ignores it per-agent; check the repo-level tree doesn't have it staged.

---

## 3. Fragile logic

### 3.1 `scaffold._validate_agent_name` uses `startswith` for path containment — FRAGILE — ✅ FIXED
**File:** `agent_builder/tools/scaffold.py:87-91`

```python
resolved = (Path(output_base) / agent_name).resolve()
base_resolved = Path(output_base).resolve()
if not str(resolved).startswith(str(base_resolved)):
```

`startswith` on stringified paths is the exact anti-pattern that lets `C:\foo2\x` match base `C:\foo`. The concrete regex guard (`^[a-z0-9][a-z0-9-]*$`) makes this unreachable today, but `remove_agent.py:43-49` and `rollback.py::_validate_target` already use the correct `resolved.relative_to(base)` pattern. Converge on the safe pattern everywhere.

### 3.2 `safety_hook` substring-matching is advisory at best — FRAGILE
**File:** `templates/agent_main.py.tmpl:217-237`

Known and documented (double-check A2). Still worth restating as a cleanup target: `rm  -rf /` (double space), `X=rm; $X -rf /`, `base64 -d | bash`, `curl … | sh` all bypass. `.env` match misses `%APPDATA%\.env`. The hook gives users a false sense of safety proportional to its confidence; before public release either strengthen it (AST-parse shell, canonicalize paths) or demote its docs to "defense-in-depth, not a sandbox."

### 3.3 Test-agent's string-replace contract leaks through `finally` but not process-death — FRAGILE
Double-check.md B4 already calls this out. Fix tied to 1.4.

### 3.4 `_audit_logger` attaches a FileHandler at import time — FRAGILE
**File:** `agent_builder/tools/self_heal.py:32-41`

Running any test that imports `self_heal` opens `agent_builder/self-heal.log` and attaches a module-level FileHandler. Tests don't close it (no fixture tears it down). Multiple test runs pile handlers on disk handles. Minor leak; bigger issue is the log file is created in the *real* `agent_builder/` directory during tests rather than `tmp_path`. Move logger setup into a lazy factory called from `propose_self_change()`.

### 3.5 `_cli_sweep` double-scans — FRAGILE
**File:** `agent_builder/builder.py:428-450`

Calls `sweep_artifacts(dry_run=True)` for the summary, then again with `dry_run=False`. Filesystem state can change between. If a new `.bak-<stamp>` appears between the two scans it is deleted without showing up in the user-approved list (or vice versa — approved file vanishes). Low probability; the fix is to capture the file list from the dry run and pass it to a pure-delete pass.

### 3.6 `_confirm` vs `asyncio.to_thread(input, ...)` — FRAGILE
**Files:** `agent_builder/builder.py:388-393` (sync `input()`), `agent_builder/builder.py:297` (async wrapper)

Direct `input()` inside `async def _cli_remove` will block the event loop. Not a practical bug today because nothing else is running on that loop when `_cli_remove` is called (it's an early-exit CLI path). But if a future caller schedules something concurrently, it deadlocks. Cheap fix: wrap `_confirm` in `asyncio.to_thread` or make it sync-only and don't call it from async contexts.

### 3.7 `_find_bak_files` scans the entire tree with `rglob("*")` — FRAGILE
**File:** `agent_builder/cleanup.py:43-51`

Walks every file under `agent_builder/` and `output/`. On big repos with many agents this is O(files). Not worth fixing until it's slow; flagging only because the default user pattern is "run `--sweep` on schedule" and it currently duplicates the scan (3.5).

### 3.8 `build_claude_md` writes unconditionally even when identity content didn't change — FRAGILE — ✅ FIXED
**File:** `agent_builder/utils.py:206-208`

Every builder startup (and every generated agent startup) rewrites `CLAUDE.md`. `mtime` thrashes on every launch, which is visible to file watchers / IDEs and can retrigger tooling (reload plugins, rerun lint, etc.). Cheap fix: read the existing file, skip the write if `combined` matches.

---

## 4. Complexity / structure

### 4.1 `builder.py::_run_one_query` is a 90-line if/elif/for nest — COMPLEXITY
Dispatch `AssistantMessage` / `ResultMessage` / `SystemMessage` all in one function, with spinner pausing, logging, verbose printing, and token accumulation interleaved. Split into three handlers (`_handle_assistant`, `_handle_result`, `_handle_system`) sharing a context object, and the spinner management becomes obvious.

Same shape exists in `templates/agent_main.py.tmpl::_drain_responses` — factor once, inline into both locations.

### 4.2 `scaffold_agent` is a single 100-line function — COMPLEXITY
Mixes: name validation, dir creation, template read, placeholder presence check, `.replace` chain, post-substitution unfilled-placeholder check, env_example write, gitignore write. Extract:

- `_render_template(template_str, ctx) -> str` — just the `.replace` and unfilled guard
- `_assemble_template_context(args) -> dict` — the `cli_mode`, `description_for_help`, `repr(...)` dance

The unit tests today hit all this through `scaffold_agent(...)`. Extraction makes each test cheaper and the function's intent obvious.

### 4.3 `test_agent::test_agent` is long and has a mix of concerns — COMPLEXITY
Sets logging, builds CLAUDE.md, flips TEST_MODE, loads tools module, determines `has_custom_tools`, builds options, loops prompts, summarises. Breakable along the natural seams:

- `_prepare_for_test(agent_dir) -> (logger, tools_server, has_custom_tools)`
- `_build_test_options(...) -> ClaudeAgentOptions`
- `_summarise_results(results) -> str`

Reduces the main function to a dozen-line orchestrator.

### 4.4 Template file is the source of truth *and* the thing under test — COMPLEXITY
`templates/agent_main.py.tmpl` carries 400 lines including inlined Spinner, safety_hook, build_claude_md, _drain_responses. Every new feature (token readout, log rotation, cli_mode dispatch) had to be placeholdered in, and every test that covers template behaviour has to re-parse the rendered output. Consider:

- Split the template into smaller files: `agent_main.tmpl` (the tiny entry point), `_agent_runtime.py` (Spinner, safety, drain) copied verbatim at scaffold time.
- Or dedupe to the `agent_builder.utils` import model (see 2.1).

### 4.5 Self-heal whitelist logic is correct but scattered — COMPLEXITY
Three separate structures: `ALLOWED_SUBDIRS`, `ALLOWED_TOP_FILES`, `DENY_FILES`. The function body checks rejected shapes (absolute, drive letter), walks them, decides. The logic is maybe a dozen lines too long for what it does. Refactor into a single `_is_allowed_target(rel_inside) -> bool | str` helper.

### 4.6 `_batch_run` has no per-prompt failure isolation — FRAGILE / structure — ✅ FIXED
**File:** `agent_builder/builder.py:346-358`

If `await _run_one_query(...)` raises in the middle of a batch, the remaining prompts never execute. Likely unintentional for a batch mode — users running `--spec` with 5 prompts want at least partial success. Wrap the call in try/except and report which prompts failed at the end.

---

## 5. Cleanup for public release

### 5.1 Docs files that shouldn't ship — CLEANUP
- `double-check.md` is valuable *internal* material. Consider moving to `docs/` or dropping from the top-level so the first-impression directory is `README / CHANGELOG / LICENSE / TODO / CLAUDE.md`.
- `TODO.md` is fine at top-level but currently mixes shipped items with roadmap; the "Shipped in v0.7.0" section belongs in the CHANGELOG.

### 5.2 `agent_builder/self-heal.log` is an empty file checked into git — CLEANUP
Zero bytes, but it's in the working tree. Either `.gitignore` it (it's a *log* — treat like all logs) or make the logger lazy-create (see 3.4).

### 5.3 `screenshots/` at repo root is a cross-concern — CLEANUP
Only used by one specific generated agent (per `.gitignore:36` comment). Doesn't belong at the repo root — belongs next to that agent under `output/`. Alternatively, make each generated agent that takes screenshots write to its own `output/<name>/screenshots/`.

### 5.4 `docs/superpowers/...` dir — CLEANUP
Design specs/plans from the initial build. They're historical. Either move to an `archive/` subdir, or inline the interesting parts into CLAUDE.md and delete.

### 5.5 Hand-maintained counts in README/CLAUDE.md — CLEANUP
README says `42 tests`, CLAUDE.md says `180+`, actual count differs again. Drop the specific numbers.

### 5.6 `claude_agent_sdk_playground.egg-info/` directory checked in — CLEANUP
Standard setuptools build artifact — should be `.gitignore`d (it is via `*.egg-info/`), but a tree is present in the current working copy. Remove from index: `git rm -r --cached claude_agent_sdk_playground.egg-info/`.

### 5.7 Blocked-patterns list feels incomplete for public use — CLEANUP — ✅ FIXED
`templates/agent_main.py.tmpl:217-237`:

- Unix: no `/etc/shadow`, `/etc/passwd`, `~/.aws/credentials`, `sudo`, `chmod 777 /`.
- Windows: no `%APPDATA%\Microsoft\Credentials`, `NTUSER.DAT`, `reg delete` patterns.
- macOS: no Keychain paths.

Either expand the list with a clear "not a sandbox" banner, or pull the list into a versioned data file that users can extend.

### 5.8 `docs/` vs `README.md` overlap — CLEANUP
Verify `docs/` still has the content that belongs to the public. If it's purely internal design, prefix with `docs/internal/`.

### 5.9 Builder `SOUL.md` / `MEMORY.md` are stubs — CLEANUP
`MEMORY.md` says "No agents built yet" even though `ez-read` exists in the registry. TODO.md already flags "Builder's own MEMORY.md never updates itself". Decide: either auto-update, or remove the placeholder line so it reads as general-purpose.

### 5.10 `_cli_doctor` output swallows WARNs in the exit-code summary — CLEANUP — ✅ FIXED
**File:** `agent_builder/builder.py:453-462`

Final summary prints `OK` or `N FAIL`. WARNs are invisible to a CI operator scanning the last line. Include a `W WARN` count alongside the FAIL count:
```
Health check: 0 FAIL, 2 WARN
```

### 5.11 `agent_builder/__init__.py` is 91 bytes — check content — CLEANUP
Not read; trivial size. Confirm it doesn't re-export internals that tighten the public surface unintentionally.

---

## 6. Security-sensitive items (defer to double-check.md plus:)

### 6.1 `WebFetch` / `WebSearch` in builder's `allowed_tools` — deferred decision
Confirmed live (`builder.py:133`). No URL allow-list; user prompts containing URLs can trigger outbound fetch. Publicly released without a gate, a user pasting a malicious URL in discovery could exfiltrate context. Mitigations to consider:

- Env var gate `ENABLE_WEB_TOOLS=1` — default off for public build.
- Domain allow-list (official Anthropic, PyPI, MDN) with explicit "allow this domain once" prompt for others.

### 6.2 `acceptEdits` on builder is broader than generated-agent safety — flagged
Double-check F2 notes this. For public release, document prominently in README: "the builder agent edits files under its cwd without prompting. Run from a dedicated working directory, not your home dir."

### 6.3 Self-heal can edit `self_heal.py` — see double-check F5 — ✅ FIXED
Trivial fix: add `"tools/self_heal.py"` to `DENY_FILES` (currently only `registry/agents.json`). One-line change.

### 6.4 Path-validator divergence — noted in 3.1
Three validators (`scaffold._validate_agent_name`, `remove_agent` inline, `rollback._validate_target`, `self_heal._validate_target`) share overlapping guards with slightly different implementations. Consolidate into `agent_builder/paths.py::validate_relative_to_base(path, allowed_bases)`.

---

## 7. Test-coverage gaps (beyond double-check.md G)

- **No tests for `_expand_menu_choice` / `_menu_text`.** `builder.py:232-284`. Any refactor to menu wording can silently drop a route.
- **No test that `scaffold._validate_agent_name` rejects the `C:\foo2` class of `startswith` bypass** — pre-emptive guard.
- **No test for `edit_agent` / `self_heal` backup collision** (1.5). Easy `freeze_time` or monkeypatch.
- **No test asserting doctor catches `{{builder_version}}` drift** (1.2). Drift would pass today.
- **No test for `_drain_responses` inside a generated agent** (only AST wiring test). A smoke test with a mock SDK would cost little.
- **No test that a generated agent's `tools.py` only swaps module-level `TEST_MODE`** (1.4). Add a case where the user's tool body contains the literal string.

---

## 8. Prioritized fix list for public release

| # | Item | Severity | Effort | Must-ship-fix? |
|---|---|---|---|---|
| 1 | Sync `EXPECTED_TEMPLATE_PLACEHOLDERS` with scaffold (1.2) | BUG | XS | yes |
| 2 | Add `user_md` to `write_identity` schema (1.1) | BUG | XS | yes |
| 3 | Ungit `agent_builder/CLAUDE.md`, `self-heal.log`, `.egg-info` (2.6, 5.2, 5.6) | CLEANUP | XS | yes |
| 4 | Update README tool count + test count (2.4, 2.5) | DRIFT | XS | yes |
| 5 | Add `tools/self_heal.py` to self-heal deny list (6.3) | FRAGILE | XS | yes |
| 6 | Fix `.bak` sub-second collision in `edit_agent` / `self_heal` (1.5) | BUG | S | yes |
| 7 | Consolidate path validators (3.1, 6.4) | FRAGILE | S | no (nice-to-have) |
| 8 | Delete dead `test_prompts` branch in `format_tool_call` (1.6) | CLEANUP | XS | no |
| 9 | Replace `_set_test_mode` file mutation with env var (1.4) | FRAGILE | M | no (v0.8.0) |
| 10 | Dedupe Spinner/format_tool_call/build_claude_md (2.1) | DRIFT | M | no (v0.8.0) |
| 11 | Gate `WebFetch`/`WebSearch` behind env var (6.1) | SECURITY | S | discuss |
| 12 | Expand `safety_hook` + prominent "not a sandbox" note (3.2, 5.7) | FRAGILE | S | yes (docs at least) |
| 13 | Per-prompt failure isolation in `_batch_run` (4.6) | FRAGILE | XS | yes |
| 14 | Complexity refactors (4.1–4.5) | COMPLEXITY | L | no (post-release) |

"Must-ship-fix" = a user of v0.7.0 can hit this within their first session. Everything else is hygiene that v0.8.0 can carry.

---

## 9. One-line summary per area

- **tools/** — correct, conservative, test-heavy. Main smells: four different validators, three places that write backups with slightly different semantics.
- **builder.py** — the `_run_one_query` dispatcher and CLI argparse both want splitting; direct CLI helpers are clean.
- **templates/agent_main.py.tmpl** — 400-line monolith. The dedup-vs-inline decision is the biggest structural call for v0.8.0.
- **cleanup.py / doctor.py** — clean, single-purpose, easy to extend. Doctor's one real job (placeholder drift) is broken — see 1.2.
- **tests/** — good breadth; missing targeted tests for drift guards (1.2), backup collisions (1.5), safety_hook bypasses (3.2), menu (5.10).
- **docs (README / CLAUDE.md / double-check.md / CHANGELOG / TODO)** — all written; staleness in README numbers; double-check material belongs in `docs/`.

Bottom line: no showstoppers for v0.7.0 → public. Ship the XS/S "must-ship" row above before tagging. Everything below is v0.8.0 polish.
