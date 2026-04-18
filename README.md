# claude-agent-sdk-playground

A meta-agent that builds Claude Agent SDK agents through conversation.

## What it does

Agent Builder is an interactive CLI built on the Claude Agent SDK (Python). You describe an agent you want; it asks clarifying questions, designs custom tools, writes identity files (`AGENT.md` / `SOUL.md` / `MEMORY.md` / optional `USER.md`), scaffolds a runnable Python agent under `output/<agent-name>/`, exercises that agent against mock tool outputs in a `TEST_MODE` sandbox, and registers it. The generated agent is a self-contained Python project you can run on its own.

## Why

Identity-driven agents (separate `AGENT.md` operating manual, `SOUL.md` personality, `MEMORY.md` running context) are a useful pattern, but writing them by hand for every new agent is repetitive. This project clones that pattern from the my.claw single-agent setup and turns it into a generator: one builder, many specialised agents, all sharing the same identity / tool / spinner contract. It also enforces a `TEST_MODE` discipline on every generated tool so a new agent can be smoke-tested without live API calls or real side effects.

## Quickstart

Requires Python >= 3.10 and an `ANTHROPIC_API_KEY`.

```bash
git clone <this-repo>
cd claude-agent-sdk-playground
pip install -e ".[dev]"
```

Run the builder:

```bash
# Interactive chat loop (default)
python -m agent_builder.builder
python -m agent_builder.builder --verbose   # raw SDK messages, tool inputs, token/cost info

# Single prompt, exit when done
python -m agent_builder.builder --prompt "build me a markdown summariser called md-summary"

# Batch of prompts from a JSON spec
python -m agent_builder.builder --spec build-specs/md-summary.json
# spec: {"prompt": "..."}  or  {"prompts": ["...","..."]}

# Direct cleanup — no SDK / no cost, instant
python -m agent_builder.builder --remove md-summary
python -m agent_builder.builder --remove a --remove b
python -m agent_builder.builder --purge-all            # every agent in the registry
python -m agent_builder.builder --purge-all --yes      # skip confirmation (scripts / CI)
```

The builder reads `ANTHROPIC_API_KEY` from your environment. Each generated agent has its own `.env` (template at `agent_builder/templates/env_example.tmpl`).

Building takes time — typically 3-10 minutes end to end, with Phase 5 (testing) alone adding 1-3 min per test prompt. The spinner shows the current phase (`Phase 4: scaffolding files`, `Phase 5: testing agent`, ...) with elapsed seconds, and a one-line banner fires when each phase begins.

## Architecture

### Identity-driven agents

Every agent in this repo (the builder itself and every agent it produces) is defined by four markdown files loaded as its system prompt:

- `AGENT.md` — operating manual: purpose, tools, workflow, rules
- `SOUL.md` — personality, tone, communication style
- `MEMORY.md` — seeded context, running log
- `USER.md` — optional, user personal info

`agent_builder/utils.py:build_claude_md` concatenates these (with `---` separators and a "do not edit" header) into a single `CLAUDE.md`. The SDK loads it via `setting_sources=["project"]`. Both `builder.py` and generated agents call `build_claude_md` on every startup, so the `CLAUDE.md` is always derived. **`CLAUDE.md` is auto-generated and git-ignored — always edit the source `.md` files.**

### The 6-phase build workflow

The builder's own `AGENT.md` enforces this sequence:

1. **Discovery** — one question at a time: purpose, name (`^[a-z0-9][a-z0-9-]*$`), task shape, file/command access needs.
2. **Tool Design** — propose tools with input schemas; every tool must have a `TEST_MODE` mock branch and return MCP-shaped content.
3. **Identity** — draft `AGENT.md`, `SOUL.md`, `MEMORY.md`, and `USER.md` (only when warranted).
4. **Generation** — call `scaffold_agent` -> `write_identity` -> `write_tools` -> `registry add`, in that exact order.
5. **Test** — call `test_agent` with 2-3 prompts (preferably as `{"prompt": ..., "expected_tools": [...]}`); the full transcript is appended to `output/<name>/test-run.log`.
6. **Handoff** — print the run command for the new agent.

A removal flow (`remove_agent`) is also supported, with explicit confirmation required before deleting.

### The 6 builder tools (MCP server)

`agent_builder/tools/__init__.py` assembles one in-process SDK MCP server (`builder_tools_server`) from six `@tool`-decorated async functions:

- `scaffold_agent` — validates `agent_name`, creates `output/<name>/` from `templates/agent_main.py.tmpl`, writes `.env.example` and `.gitignore`. Accepts `tools_list`, `allowed_tools_list`, `permission_mode` so the generated `agent.py` is valid Python with no unfilled placeholders.
- `write_identity` — writes `AGENT.md` / `SOUL.md` / `MEMORY.md` / `USER.md` into the agent dir.
- `write_tools` — writes `tools.py`, prepending a fixed `TOOLS_HEADER` (imports + `TEST_MODE = False`); the caller must NOT include those.
- `test_agent` — flips `TEST_MODE = True` in the agent's `tools.py`, dynamically imports it, runs each prompt through `query()`, and always restores `TEST_MODE = False` in a `finally` block. Pass/fail asserts on `subtype=success`, no permission denials, no errors, at least one custom tool call, and all `expected_tools` invoked.
- `registry` — `add` / `remove` / `list` / `describe` against `agent_builder/registry/agents.json`.
- `remove_agent` — same name validation as `scaffold_agent`, then `shutil.rmtree`s `output/<name>/` and drops the registry entry in one call.

The builder also has `Read`, `Write`, `Edit`, `Glob`, `Grep`, and `Bash` available, with `permission_mode="acceptEdits"`.

### The `TEST_MODE` contract for generated tools

Every tool in a generated agent's `tools.py` must:

- Begin with `if TEST_MODE: return {...}` returning a deterministic mock so `test_agent` can exercise it offline.
- Return MCP shape `{"content": [{"type": "text", "text": ...}]}`.
- Signal failure via `is_error: True` rather than raising.
- Be registered at the bottom of the file via `tools_server = create_sdk_mcp_server(...)`.
- Omit the `import` block and `TEST_MODE = False` line — `write_tools` prepends them via `TOOLS_HEADER`.

## Example session

```
$ python -m agent_builder.builder

  Agent Builder ready. Describe what agent you'd like to build.
  Type 'exit' to quit.

> i want an agent that reviews python files for unused imports

[Discovery] What should the agent be called? (lowercase, hyphens only)
> import-checker
[Discovery] Should it modify files, or only report findings?
> only report

[Tool Design] Proposing one custom tool: scan_imports(path) -> list of unused
  symbols per file. TEST_MODE will return a fixed two-file fixture.
  Permission tier: read-only (Read, Glob, Grep), permission_mode=dontAsk.
  Confirm?
> yes

[Generation]
  [Tool: scaffold_agent] agent_name=import-checker
  [Tool: write_identity] agent_name=import-checker
  [Tool: write_tools] agent_name=import-checker
  [Tool: registry] action=add

[Test] Running 2 prompts against TEST_MODE...
  [Tool: test_agent] agent_name=import-checker
  Both prompts passed. Transcript at output/import-checker/test-run.log.

Agent ready at output/import-checker/. Run it with:
  python output/import-checker/agent.py
```

The exact prompts the builder issues vary per agent; the phases above are the contract.

## Testing

Run the suite with:

```bash
pytest                                 # all 42 tests as of v0.2.0
pytest tests/test_scaffold.py          # one file
pytest -k "scaffold"                   # by keyword
```

`pytest-asyncio` runs in auto mode (`tests/conftest.py` provides `tmp_agent_dir` and `tmp_agent_dir_with_user` fixtures). Tool tests call the underlying async function directly, not the `@tool`-wrapped version. Coverage spans `scaffold_agent`, `write_identity`, `write_tools`, `remove_agent`, the `registry`, `build_claude_md`, and `format_tool_call`.

## Generated agents

Each invocation of `scaffold_agent` produces:

```
output/<name>/
  agent.py          # from templates/agent_main.py.tmpl, all placeholders filled
  tools.py          # written by write_tools, TOOLS_HEADER + your code
  AGENT.md
  SOUL.md
  MEMORY.md
  USER.md           # optional
  CLAUDE.md         # auto-generated on every run, git-ignored
  .env.example
  .gitignore
  test-run.log      # appended to by test_agent
```

Run a generated agent:

```bash
python output/<name>/agent.py
python output/<name>/agent.py --verbose
```

Each generated `agent.py` rebuilds its `CLAUDE.md` from the four identity files at startup, registers a `PreToolUse` `safety_hook` on `Bash`, `Write`, and `Edit` (blocks destructive bash patterns like `rm -rf /`, `DROP TABLE`, `DELETE FROM`, `> /dev/sda`, fork bombs; and refuses writes to sensitive paths like `.env`, `.git/`, `pyproject.toml`, `package.json`, `.ssh/`, `id_rsa`, `id_ed25519`, `credentials`). It runs an interactive REPL with `max_turns`/`max_budget_usd` chosen at scaffold time (defaults 25 / $1.00). Both a per-agent log at `output/<name>/<name>.log` and a per-test-run log at `output/<name>/test-run.log` are maintained automatically.

A `Spinner` (inlined into the template, not imported from `agent_builder`) shows `| / - \` frames on stderr with an elapsed-seconds counter; its label flips to `running <tool>` while a tool executes and back to `thinking` between turns. `format_tool_call` renders one-line previews per tool call (picks the most informative field: `command`, `file_path`, `pattern`, `url`, `action`, ...; truncates to 80 chars; strips the `mcp__<server>__` prefix).

## Adding a new builder tool

1. Create `agent_builder/tools/<name>.py` with an async function and a `@tool`-decorated wrapper.
2. Import and register it in `agent_builder/tools/__init__.py`.
3. Add `"mcp__builder_tools__<name>"` to `allowed_tools` in `agent_builder/builder.py`.
4. Add tests under `tests/`.

## Contributing

Edit source identity files (`AGENT.md` / `SOUL.md` / `MEMORY.md`), never the generated `CLAUDE.md`. Run `pytest` before opening a PR. Keep generated agent output (`output/`) out of commits.

Optional: enable the shared pre-commit hook (runs pytest before every commit):

```bash
git config core.hooksPath .githooks
```

The activation is per-clone — each contributor opts in. The hook skips gracefully if `python` or `pytest` aren't on `PATH`, so it won't lock you out of committing when you don't have the dev env active.

## License

[PolyForm Noncommercial 1.0.0](LICENSE). Free to use, modify, and share for any noncommercial purpose (personal projects, research, education, hobby, public-interest organisations). Commercial use is not granted under this licence — contact the author if you want a commercial licence.
