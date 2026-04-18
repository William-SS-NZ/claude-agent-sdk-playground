# Changelog

All notable changes to this project are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.5.1] - 2026-04-18

### Fixed
- **`ModuleNotFoundError: No module named 'tools'` on first run of generated agents.** The model could call `scaffold_agent` + `write_identity` + `registry add` while skipping `write_tools` (especially for read-only agents that "don't need custom tools"). The generated `agent.py` always does `from tools import tools_server`, so this produced silent half-built agents that crashed at runtime. Three coordinated fixes close the gap:
  - `registry add` now validates the agent directory before sealing the build. If any of `agent.py`, `tools.py`, `AGENT.md`, `SOUL.md`, `MEMORY.md` is missing, it returns `is_error` listing exactly what's gone, so the model can self-correct by re-running the missing tool. Internal `skip_validation` kwarg available for unit tests (not exposed via the MCP schema).
  - `write_tools` now accepts an empty / whitespace-only / missing `tools_code` and emits a no-op `tools_server = create_sdk_mcp_server(name="agent-tools", version="1.0.0", tools=[])` stub so agents that genuinely need no custom tools still produce a valid `tools.py`.
  - `AGENT.md` Phase 4 hardened: all four Phase 4 tools are mandatory (call `write_tools` with empty `tools_code` if no custom tools), and any `is_error` from any Phase 4 tool MUST stop the chain rather than silently proceed.

### Added
- **`test_agent` now handles agents with no custom tools.** It introspects the loaded `tools_server` and, when it finds zero registered tools, drops the "must call at least one custom tool" pass criterion and broadens `allowed_tools` to the built-in Read/Glob/Grep/Edit/Write/Bash so a read-only agent (e.g. a markdown summariser) can still do meaningful work in the test. AGENT.md now tells the builder to always run `test_agent`, even for empty-tools agents — this catches CLAUDE.md generation, identity-file, and prompt-following bugs that would otherwise surface only at runtime.
- 7 new tests: `write_tools` empty/whitespace/missing `tools_code` cases (3), build-completeness validator (4).

## [0.5.0] - 2026-04-18

### Added
- **`rollback` MCP tool** with `list` and `restore` actions over the `.bak-<timestamp>` files written by `edit_agent` and `propose_self_change`. Restore copies a fresh `.bak-<now>` of the current target before overwriting, so the restore itself is reversible. Path-traversal hardened: target must resolve under the repo root / `agent_builder/` / `output/`; `backup_name` must be a plain basename in the same directory and must match the target's basename (no cross-file restores like `AGENT.md.bak-...` over `tools.py`).
- **`.env` auto-load in generated agents**. Template now does a guarded `from dotenv import load_dotenv` (no-op fallback if dotenv isn't installed) and calls `load_dotenv(AGENT_DIR / ".env")` first thing in `main()`, before SDK options are built. `python-dotenv>=1.0` moved from dev extras into core dependencies.
- **`env_example.tmpl` documents the CLI-login fallback** so users know they can leave `ANTHROPIC_API_KEY=` empty and lean on `claude login` subscription auth.
- **Registry schema extension**: `add` now accepts `max_turns`, `max_budget_usd`, `permission_mode` (all optional, all preserved across partial-update calls). Every entry carries an `updated_at` ISO date alongside `created`. `describe` surfaces all of these. `edit_agent` bumps `updated_at` on a successful edit (silent no-op if the agent isn't registered).
- **Template `build_claude_md` regression coverage** — the inlined copy in `agent_main.py.tmpl` is now exercised against the same scenarios as the `agent_builder/utils.py` version (header write, required-section content, optional USER.md, raises on missing AGENT.md).
- **README** mentions `python -m agent_builder.builder --help` so all CLI flags are discoverable in one line.

### Changed
- **AGENT.md Phase 4 partial-failure recovery** is now a single branched question (`A) clean up + restart  B) repair in place  C) abandon`) instead of two sequential confirmations. One round-trip, one decision.

## [0.4.1] - 2026-04-18

### Added
- `--remove NAME` (repeatable) and `--purge-all` CLI flags on `python -m agent_builder.builder`. These call the `remove_agent` tool's underlying function directly — no SDK subprocess, no model roundtrip, no cost — so mass cleanup is instant. Both prompt for confirmation by default; pass `--yes` to skip (useful from scripts / CI). `--remove` and `--purge-all` are mutually exclusive with `--prompt` / `--spec`.

## [0.4.0] - 2026-04-18

### Added
- `edit_agent` MCP tool for updating an existing agent's identity or `tools.py` in place. Only supplied fields overwrite; every changed file gets a `.bak-<timestamp>`. `tools_code` receives the canonical `TOOLS_HEADER` prepended, matching the `write_tools` contract. Does not touch `agent.py`, `.env.example`, or `.gitignore` (those stay scaffold-time artifacts).
- `AGENT.md` gains an "Editing Existing Agents" section instructing the builder to read before proposing, only write changed fields, and tell the user to restart.
- **Non-interactive builder modes**: `python -m agent_builder.builder --prompt "..."` sends a single prompt and exits. `--spec spec.json` runs a batch of prompts (spec shape: `{"prompt": "..."}` or `{"prompts": ["...","..."]}` or a bare JSON string). Lets you build agents from a script or CI pipeline without entering the chat loop.
- **Phase-aware progress**: spinner label now reflects what the builder is actually doing (`Phase 4: scaffolding files`, `Phase 5: testing agent (can take 1-3 min)`, etc.) rather than a flat `thinking`. First use of each phase-anchoring tool prints a banner like `── Phase 4: scaffolding files ──`. Final result line includes elapsed seconds alongside the cost readout.
- **Live token + cost readout** next to the spinner: `thinking ( 12.3s) | 45,678 tok | ~$0.21 | ~$1.05/min`. The spinner accumulates `input_tokens` / `output_tokens` from streamed `AssistantMessage.usage` and estimates cost at Claude Opus 4.x pricing (`$15/MT input + $75/MT output`) with a `~$` prefix to indicate the estimate. When `ResultMessage.total_cost_usd` arrives, the spinner switches to the authoritative value and drops the tilde. The same readout is inlined into every generated agent's REPL via the template.
- **Scaffold unfilled-placeholder guard**: scaffold aborts with a clear error if any `{{...}}` survives template substitution, rather than writing a syntactically broken `agent.py` that `NameError`s on first run.
- **Graceful Ctrl+C**: `KeyboardInterrupt` at the top-level asyncio loop exits cleanly; `KeyboardInterrupt` during a response cancels that response and returns to the prompt without losing the session.
- Regression tests for `test_agent`: `TEST_MODE = False` must be restored in the `tools.py` of the agent under test even when `_load_tools_server` crashes or a prompt run raises. Previously only implicit via the `finally` block — now explicitly covered.
- Tests for the spec loader and phase label/banner helpers.

### Changed
- `AGENT.md` Phase 1 hardened: the builder must ask for the agent name explicitly and wait for the user's reply before proceeding, even when the initial description makes a name obvious. A prior build auto-named an agent without confirmation; this prevents that.
- `AGENT.md` Phase 5 warns up front that testing takes 1-3 minutes per prompt, so users know why the spinner sits on `Phase 5: testing agent` for a while.

### Fixed
- Scaffolded `output/<name>/agent.py` is now always parseable Python — the unfilled-placeholder guard catches the case where a builder session was started with older in-process code and missed a newer placeholder in the template.

## [0.3.0] - 2026-04-18

### Added
- **Self-heal**: `propose_self_change` MCP tool lets the builder patch its own identity/tools/template/utils after a hard stdin confirmation. Whitelisted scope, `.bak-<timestamp>` backups, audit log at `agent_builder/self-heal.log`.
- **Remove agent**: `remove_agent` MCP tool deletes an `output/<name>/` directory and drops its registry entry in one call. Reuses scaffold's path-traversal validator.
- **Registry `remove` action** plus `add` that now deduplicates on name (upsert instead of silent duplicate).
- **Stricter `test_agent`**: pass criteria require `subtype=success` AND no `permission_denials` AND no `errors` AND at least one custom-tool call. `expected_tools` can be supplied per prompt. Full transcript appended to `output/<name>/test-run.log`. `max_turns` is now a parameter (default 10, up from hardcoded 5).
- **Spinner** with elapsed-seconds counter and `running <tool>` label while a tool executes. Available both in the builder and every generated agent via the template.
- **One-line tool-call previews** via `format_tool_call` (picks the most informative field per tool, strips `mcp__<server>__` prefix, truncates to 80 chars).
- **Default logger in the generated-agent template** — every new agent emits a file log at `output/<name>/<name>.log` with user inputs, tool uses, errors, and fatal tracebacks.
- **Widened `safety_hook`** in the template — also runs on `Write` and `Edit`, refuses to touch sensitive paths (`.env`, `.git/`, `pyproject.toml`, `package.json`, `.ssh/`, `id_rsa`, `id_ed25519`, `credentials`). Bash pattern list now also includes a fork-bomb signature.
- **`write_identity` 8191-char guard** — warns when combined identity content exceeds 6000 chars, to stay clear of Windows `CreateProcessW` command-line limits.
- **`scaffold_agent` accepts `max_turns` and `max_budget_usd`** so iterative agents ship with sensible per-agent caps rather than needing hand-edits.
- **README.md**, **LICENSE (PolyForm Noncommercial 1.0.0)**, **GitHub Actions CI** (pytest on Python 3.10/3.11/3.12), **shared pre-commit hook** at `.githooks/pre-commit`.
- **Tests** — 55 cases covering scaffold placeholders, registry upsert/remove, remove_agent path traversal, self-heal whitelist/drive-letter/ambiguous edits, formatter truncation.

### Changed
- `scaffold_agent` now fills every template placeholder (`{{tools_list}}`, `{{allowed_tools_list}}`, `{{permission_mode}}`, `{{max_turns}}`, `{{max_budget_usd}}`). Previously only `{{agent_name}}` was substituted, leaving the generated `agent.py` as invalid Python until the builder hand-patched it.
- `test_agent` is now wrapped via post-def `test_agent_tool` (consistent with other tools); the async function stays directly callable.
- `pyproject.toml`: package discovery scoped to `agent_builder*`, pytest confined to `tests/`, dependencies now have lower-bound version pins, license and author metadata added, version bumped to 0.3.0.
- Template's `build_claude_md` now raises `FileNotFoundError` on missing required identity files (matches `agent_builder/utils.py`); it previously silently skipped.

### Fixed
- Correct `CLAUDE.md` architecture note: in-process MCP tools see the Python process cwd, not the `cwd=` on `ClaudeAgentOptions` (that flag only affects the CLI subprocess). Agents land in repo-root `output/`, not `agent_builder/output/`.
- `AGENT.md` Phase 4 now tells the builder what to do on generation failure partway through the `scaffold → write_identity → write_tools → registry` chain (ask whether to call `remove_agent` to clear the orphan directory).

## [0.2.0] - 2026-04-18

### Added
- `remove_agent` tool with path-traversal safety.

### Changed
- `registry.add` now deduplicates on agent name.

## [0.1.0] - 2026-04-13

Initial release: Agent Builder CLI, six-phase workflow, `scaffold_agent` / `write_identity` / `write_tools` / `test_agent` / `registry` tools, identity-file-driven `CLAUDE.md`.
