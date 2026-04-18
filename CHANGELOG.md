# Changelog

All notable changes to this project are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `edit_agent` MCP tool for updating an existing agent's identity or `tools.py` in place. Only supplied fields overwrite; every changed file gets a `.bak-<timestamp>`. `tools_code` receives the canonical `TOOLS_HEADER` prepended, matching the `write_tools` contract. Does not touch `agent.py`, `.env.example`, or `.gitignore` (those stay scaffold-time artifacts).
- `AGENT.md` gains an "Editing Existing Agents" section instructing the builder to read before proposing, only write changed fields, and tell the user to restart.
- Regression tests for `test_agent`: `TEST_MODE = False` must be restored in the `tools.py` of the agent under test even when `_load_tools_server` crashes or a prompt run raises. Previously only implicit via the `finally` block — now explicitly covered.

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
