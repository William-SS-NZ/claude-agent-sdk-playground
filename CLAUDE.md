# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Agent Builder — meta-agent that builds Claude Agent SDK agents through conversation. Runs as an interactive CLI. Asks user what agent they want, designs tools, writes identity files, scaffolds a runnable Python agent into `output/<agent-name>/`, tests it, registers it.

## Commands

```bash
# Install (editable + dev extras)
pip install -e ".[dev]"

# Run the Agent Builder CLI
python -m agent_builder.builder
python -m agent_builder.builder --verbose   # shows raw SDK messages, tool inputs, token/cost info

# Run a generated agent
python output/<agent-name>/agent.py

# Tests
pytest                                      # all
pytest tests/test_scaffold.py               # one file
pytest tests/test_scaffold.py::test_scaffold_rejects_invalid_name  # one test
pytest -k "scaffold"                        # by keyword
```

Requires `ANTHROPIC_API_KEY` in the agent's `.env` (template at `agent_builder/templates/env_example.tmpl`).

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
- `edit_agent` — update an existing agent's identity files or `tools.py` in place. Supplied fields replace; omitted fields are left alone. Every overwritten file gets a `.bak-<timestamp>`. `tools_code` gets the canonical `TOOLS_HEADER` prepended same as `write_tools`. Does NOT touch `agent.py`, `.env.example`, or `.gitignore` — those are scaffold-time artifacts.
- `propose_self_change` — **self-heal**.
- `rollback` — `list` and `restore` actions over the `.bak-<timestamp>` files left by `edit_agent` and `propose_self_change`. Restore writes a fresh pre-restore backup so it's itself reversible. Refuses cross-file restores (an `AGENT.md.bak-...` cannot be restored over `tools.py`) and standard path-traversal attempts. The builder can edit its own identity/tools/template/utils when it observes a workflow failure, but only after a hard stdin confirmation. Scope is whitelisted (`identity/`, `tools/`, `templates/`, `utils.py`, `builder.py`); `registry/agents.json`, `output/`, and anything outside `agent_builder/` are rejected. Writes a `.bak-<timestamp>` backup on every apply and appends to `agent_builder/self-heal.log`. Changes take effect on the next builder session — the current in-process modules are not reloaded.

Adding a new builder tool: create `agent_builder/tools/<name>.py`, import and register in `tools/__init__.py`, add to `allowed_tools` in `builder.py` as `"mcp__builder_tools__<name>"`.

### Builder UX utilities

`agent_builder/utils.py` exposes two helpers used by `builder.py` and the generated-agent template:

- `Spinner` — async stderr spinner (`|/-\\` frames) with elapsed-seconds counter, `start()` / `await stop()` / context-manager `paused()` for clean printing without smearing the line. The spinner label updates to `running <tool>` while a tool executes.
- `format_tool_call(name, input)` — one-line preview per tool call, picks the most informative field (command, file_path, pattern, url, action...), truncates to 80 chars, strips the `mcp__<server>__` prefix.

Both are inlined into `agent_main.py.tmpl` so generated agents ship with the same UX without importing from `agent_builder`.

### Generated-agent contract

Tools generated for new agents must:
- Include an `if TEST_MODE:` branch at the top returning mock data (so `test_agent` can exercise them offline)
- Return `{"content": [{"type": "text", "text": ...}]}`; signal failure with `is_error: True` rather than raising
- End `tools.py` with a `create_sdk_mcp_server(...)` call bound to the name `tools_server` (that's what `agent.py` and `test_agent` import)
- Omit imports and the `TEST_MODE = False` line — `write_tools` prepends them

The generated `agent.py` (from `templates/agent_main.py.tmpl`) wires a `PreToolUse` hook (`safety_hook`) that blocks `rm -rf /`, `DROP TABLE`, `DELETE FROM`, `> /dev/sda` in Bash. `{{agent_name}}`, `{{tools_list}}`, `{{allowed_tools_list}}`, `{{permission_mode}}` are template placeholders.

### Builder workflow (6 phases)

The builder's `AGENT.md` enforces: Discovery → Tool Design → Identity → Generation → Test → Handoff, and generation must call `scaffold_agent` → `write_identity` → `write_tools` → `registry add` in that exact order. Permission tiers (read-only / read-write / full automation) picked per agent needs.

### Path conventions

Paths use `Path(__file__).parent` throughout — run from any cwd. The `cwd=` kwarg on `ClaudeAgentOptions` only affects the CLI subprocess the SDK spawns; in-process MCP tools (which run in the same Python process as `builder.py`) see the *Python process's* cwd, which is typically the repo root. That is why generated agents land in repo-root `output/<name>/` rather than `agent_builder/output/<name>/`. Tools default to `output_base="output"` relative to the Python process cwd.

## Testing notes

- `pytest-asyncio` in auto mode; tests use `@pytest.mark.asyncio`
- `tests/conftest.py` provides `tmp_agent_dir` / `tmp_agent_dir_with_user` fixtures that seed identity files under `tmp_path/identity/`
- Tool tests call the underlying async function directly (e.g. `scaffold_agent(...)`), not the `@tool`-wrapped version
