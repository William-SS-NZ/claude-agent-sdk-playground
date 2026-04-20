# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Agent Builder — meta-agent that builds Claude Agent SDK agents through conversation. Runs as an interactive CLI. Asks user what agent they want, designs tools, writes identity files, scaffolds a runnable Python agent into `output/<agent-name>/`, tests it, registers it.

## Commands

```bash
# Install (editable + dev extras)
pip install -e ".[dev]"

# Interactive chat loop (menu on launch)
python -m agent_builder.builder
python -m agent_builder.builder -v                # raw SDK messages + cost details

# Non-interactive build
python -m agent_builder.builder -p "build me a markdown summariser called md-summary"
python -m agent_builder.builder -s build-spec.json    # {"prompt": "..."} or {"prompts": [...]}

# Direct bookkeeping (no SDK, no cost)
python -m agent_builder.builder --remove NAME         # also -r
python -m agent_builder.builder --purge-all           # also -P
python -m agent_builder.builder --sweep --older-than 7   # clean .bak files / logs / screenshots
python -m agent_builder.builder --doctor              # read-only health audit
python -m agent_builder.builder --help                # discover everything

# Run a generated agent
python output/<agent-name>/agent.py
python output/<agent-name>/agent.py -p "summarise ./README.md"   # if scaffolded cli_mode=True

# Tests
pytest                                       # full suite
pytest tests/test_scaffold.py                # one file
pytest -k "scaffold"                         # by keyword
```

Per-run builder log at `agent_builder/logs/builder-YYYYMMDD-HHMMSS.log`. Per-agent log at `output/<name>/<name>.log` (rotating 5 MB × 3 backups).

Auth: `ANTHROPIC_API_KEY` in `.env` (the generated agent auto-loads via `python-dotenv`), or fall back to the `claude login` subscription if the key is unset.

## Architecture

### Identity-driven agents

Every agent (the builder itself and every generated agent) is defined by four markdown files loaded as its system prompt:

- `AGENT.md` — operating manual: purpose, tools, workflow, rules
- `SOUL.md` — personality, tone, communication style
- `MEMORY.md` — seeded context, running log
- `USER.md` — optional, user personal info

`agent_builder/utils.py:build_claude_md` concatenates these with `---` separators into a single `CLAUDE.md`. The SDK loads `CLAUDE.md` via `setting_sources=["project"]`. **`CLAUDE.md` is auto-generated and git-ignored — always edit the source `.md` files, never `CLAUDE.md`.** Both `builder.py` and generated agents rebuild `CLAUDE.md` on every startup.

### Builder tools (MCP server)

`agent_builder/tools/__init__.py` assembles one in-process SDK MCP server (`builder_tools_server`) from nine tools. Each is a `@tool`-decorated async function wired via `create_sdk_mcp_server`. All return MCP shape `{"content": [{"type": "text", "text": ...}], "is_error"?: bool}`:

- `scaffold_agent` — validates name against `^[a-z0-9][a-z0-9-]*$` + path-traversal guard, creates `output/<name>/` with `agent.py` (from `templates/agent_main.py.tmpl`), `.env.example`, `.gitignore`. Accepts `tools_list`, `allowed_tools_list`, `permission_mode` so the generated `agent.py` is valid Python with no unfilled placeholders.
- `write_identity` — writes `AGENT.md`/`SOUL.md`/`MEMORY.md`/`USER.md` into the agent dir
- `write_tools` — writes `tools.py`, prepending the fixed `TOOLS_HEADER` (imports + `TEST_MODE = False`); the caller-supplied `tools_code` must NOT include those
- `test_agent` — flips `TEST_MODE = True` in the agent's `tools.py`, imports it dynamically via `importlib.util`, runs each prompt through `query()` with `max_turns=5`, then always restores `TEST_MODE = False` in a `finally` block
- `registry` — `add` (upserts by name), `remove`, `list`, `describe` against `agent_builder/registry/agents.json`
- `remove_agent` — safely deletes `output/<name>/` via `shutil.rmtree` and drops the registry entry in one call. Same validation as `scaffold_agent`; refuses anything resolving outside `output_base`.
- `edit_agent` — update an existing agent's identity files or `tools.py` in place. Supplied fields replace; omitted fields are left alone. Every overwritten file gets a `.bak-<timestamp>`; sub-second collision aborts the edit rather than clobbering the existing backup. `tools_code` gets the canonical `TOOLS_HEADER` prepended same as `write_tools`. Does NOT touch `agent.py`, `.env.example`, or `.gitignore` — those are scaffold-time artifacts.
- `propose_self_change` — **self-heal**. The builder can edit its own identity/tools/template/utils when it observes a workflow failure, but only after a hard stdin confirmation. Scope is whitelisted (`identity/`, `tools/`, `templates/`, `utils.py`, `builder.py`); `registry/agents.json`, `tools/self_heal.py` (so the confirmation gate can't be self-removed), `output/`, and anything outside `agent_builder/` are rejected. Writes a `.bak-<timestamp>` backup on every apply (aborts on sub-second collision rather than clobbering) and appends to `agent_builder/self-heal.log`. Changes take effect on the next builder session — the current in-process modules are not reloaded.
- `rollback` — `list` and `restore` actions over the `.bak-<timestamp>` files left by `edit_agent` and `propose_self_change`. Restore writes a fresh pre-restore backup so it's itself reversible. Refuses cross-file restores (an `AGENT.md.bak-...` cannot be restored over `tools.py`) and standard path-traversal attempts.

Adding a new builder tool: create `agent_builder/tools/<name>.py`, import and register in `tools/__init__.py`, add to `allowed_tools` in `builder.py` as `"mcp__builder_tools__<name>"`.

### Recipes library

Reusable integration components live under `agent_builder/recipes/{mcps,tools,skills}/<slug>/`. Each recipe is a directory with a `RECIPE.md` carrying frontmatter metadata (name, type, version, description, when_to_use, env_keys, oauth_scopes, allowed_tools_patterns, tags) plus type-specific siblings:

- **mcp** recipes ship `mcp.json` (an `mcp_servers`-shaped entry) and optionally `setup_auth.py.tmpl` when OAuth is required
- **tool** recipes ship `tool.py` — drop-in `@tool`-decorated code that becomes its own SDK MCP server at the generated agent's composition time
- **skill** recipes ship `skill.md` — prose appended to the target agent's `AGENT.md` (Phase G / v0.9.2)

Discovery: `list_recipes` returns a compact JSON index for the builder to consult during Phase 2.5 (Recipe Attachment). Materialization: `attach_recipe` appends the recipe to `.recipe_manifest.json` in the agent dir and calls `render_agent` to rebuild `agent.py` from that manifest. For mcp recipes the rebuild fills the `external_mcp_block` with the `mcp.json` config, appends env_keys to `.env.example` with a versioned banner, and (for OAuth) renders `setup_auth.py` from the recipe's `setup_auth.py.tmpl`.

### Template modes

`scaffold_agent` takes `mode: "cli" | "poll"` (Phase F adds `"server"`). Each mode selects a different template:

- **cli** (default) — `templates/agent_main.py.tmpl`. Interactive chat loop with optional `-p/--prompt` and `-s/--spec` for scripted runs.
- **poll** — `templates/agent_poll.py.tmpl`. Long-poll worker that iterates an `async for incoming in poll_source` loop. `scaffold_agent` renders a `_stub_poll_source()` that raises NotImplementedError; attaching a poll-capable recipe (e.g. `telegram-poll`) rewrites the stub via manifest + render_agent.
- **server** (Phase F, v0.9.1) — `templates/agent_server.py.tmpl`. FastAPI webhook receiver; refuses to scaffold without a webhook-capable recipe.

All three modes share the same identity bootstrap, spinner, safety hook, and `_drain_responses` — differences are only in the driver loop. Doctor validates each template's expected placeholders via `REQUIRED_PLACEHOLDERS_BY_MODE`. Spinner / format_tool_call / build_claude_md live in `agent_builder/utils.py`; templates import them rather than inlining (R6 dedup).

### Direct CLI helpers (no SDK, no model cost)

Three commands on `builder.py` short-circuit the SDK entirely — useful for scripts, CI, and post-incident cleanup:

- `--sweep [--older-than DAYS]` — deletes stale `.bak-<timestamp>` files under `agent_builder/` and `output/`, per-run `agent_builder/logs/builder-<timestamp>.log` files, and `screenshots/` at the repo root when every file inside is older than the cutoff. Default cutoff 7 days. Dry-run summary first; needs `--yes` to skip the confirm prompt. Implementation: `agent_builder/cleanup.py`.
- `--doctor` — read-only health audit: registry parses, every registered agent has its `output/<name>/` with all required files, output dirs without a registry entry WARN, builder's identity files exist, template has every expected `{{placeholder}}`, no generated `agent.py` carries leftover placeholders. Exit 0 when no FAIL, 1 otherwise. Implementation: `agent_builder/doctor.py`.
- `--remove NAME` / `--purge-all` — direct `remove_agent` calls without the SDK.

### Version + version stamp

`agent_builder/_version.py` is the single source of truth. It reads `importlib.metadata.version("claude-agent-sdk-playground")` with a `"unknown"` fallback for source-only checkouts. The builder's MCP server version reads from it; every generated `agent.py` stamps `GENERATED_WITH_BUILDER_VERSION = "<version>"` near the top so future tooling can detect regens from incompatible builder versions.

### Builder UX utilities

`agent_builder/utils.py` exposes two helpers used by `builder.py` and the generated-agent template:

- `Spinner` — async stderr spinner (`|/-\\` frames) with elapsed-seconds counter, `start()` / `await stop()` / context-manager `paused()` for clean printing without smearing the line. The spinner label updates to `running <tool>` while a tool executes.
- `format_tool_call(name, input)` — one-line preview per tool call, picks the most informative field (command, file_path, pattern, url, action...), truncates to 80 chars, strips the `mcp__<server>__` prefix.

Both are inlined into `agent_main.py.tmpl` so generated agents ship with the same UX without importing from `agent_builder`.

### Generated-agent contract

Tools generated for new agents must:
- Include an `if _test_mode():` branch at the top returning mock data (so `test_agent` can exercise them offline). `_test_mode()` reads `AGENT_TEST_MODE` env var; `TOOLS_HEADER` provides the helper.
- Return `{"content": [{"type": "text", "text": ...}]}`; signal failure with `is_error: True` rather than raising
- End `tools.py` with a `create_sdk_mcp_server(...)` call bound to the name `tools_server` (that's what `agent.py` and `test_agent` import)
- Omit imports and the `_test_mode()` helper — `write_tools` prepends them

The generated `agent.py` (from `templates/agent_main.py.tmpl`) wires a `PreToolUse` hook (`safety_hook`) on `Bash`, `Write`, and `Edit` — blocks destructive Bash patterns (`rm -rf /`, `DROP TABLE`, `DELETE FROM`, `> /dev/sda`, fork bomb) and refuses writes to sensitive paths (`.env`, `.git/`, `pyproject.toml`, `package.json`, `.ssh/`, `id_rsa`, `id_ed25519`, `credentials`). Template placeholders: `{{agent_name}}`, `{{agent_description}}`, `{{builder_version}}`, `{{tools_list}}`, `{{allowed_tools_list}}`, `{{permission_mode}}`, `{{max_turns}}`, `{{max_budget_usd}}`, `{{cli_args_block}}`, `{{cli_dispatch_block}}`, `{{cli_help_epilog}}`. Scaffold validates every expected placeholder is present in the template AND that none survive substitution before writing — a drift in either direction fails loudly rather than producing broken Python.

Generated `agent.py` files include a `RECIPE_PINS = {...}` dict (JSON-shaped) listing every attached recipe and its version. Empty at scaffold time; updated deterministically by `attach_recipe` via the manifest. A future `edit_agent --resync-recipes` action (v0.9.x) will compare pins against current recipe versions and offer updates.

### Builder workflow (6 phases)

The builder's `AGENT.md` enforces: Discovery → Tool Design → Identity → Generation → Test → Handoff, and generation must call `scaffold_agent` → `write_identity` → `write_tools` → `registry add` in that exact order. Permission tiers (read-only / read-write / full automation) picked per agent needs.

### Path conventions

Paths use `Path(__file__).parent` throughout — run from any cwd. The `cwd=` kwarg on `ClaudeAgentOptions` only affects the CLI subprocess the SDK spawns; in-process MCP tools (which run in the same Python process as `builder.py`) see the *Python process's* cwd, which is typically the repo root. That is why generated agents land in repo-root `output/<name>/` rather than `agent_builder/output/<name>/`. Tools default to `output_base="output"` relative to the Python process cwd.

## Testing notes

- `pytest-asyncio` in auto mode; tests use `@pytest.mark.asyncio`
- `tests/conftest.py` provides `tmp_agent_dir` / `tmp_agent_dir_with_user` fixtures that seed identity files under `tmp_path/identity/`
- Tool tests call the underlying async function directly (e.g. `scaffold_agent(...)`), not the `@tool`-wrapped version
