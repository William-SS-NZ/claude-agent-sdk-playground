# Agent Builder — Design Spec

> A standalone interactive CLI that walks users through creating purpose-built Claude Agent SDK agents via conversation.

## Goal

Build an Agent Builder — a meta-agent you run from the terminal that:
1. Asks what kind of agent you need through an interactive conversation
2. Designs custom tools, identity, and configuration based on your answers
3. Generates a complete, runnable agent in `output/{agent_name}/`
4. Test-runs the agent with mock tools to verify it works
5. Self-heals if tests fail (diagnose, explain, fix, retry)

Inspired by OpenClaw's config-first, multi-file identity architecture, built on the Claude Agent SDK for Python.

## Architecture

### Approach: Hybrid (Templates + Claude Freehand)

Templates handle structural boilerplate (imports, main loop, message processing, directory layout). Claude writes the creative parts freehand (tool handler logic, identity file content). This gives consistent structure with creative flexibility where it matters.

**Template zone** (deterministic, same every time):
- `agent.py` scaffolding: imports, `build_claude_md()`, main loop, error handling, cost display
- `@tool` decorator skeleton: name, description, schema, `TEST_MODE` branch
- `.env.example` generation
- Directory structure creation

**Claude zone** (authored per agent):
- Tool handler implementations (the actual logic inside each `@tool`)
- `AGENT.md` content (operating manual)
- `SOUL.md` content (personality)
- `MEMORY.md` content (initial context)
- `USER.md` content (optional, user info)
- Test prompts (contextual to the agent's purpose)

### Directory Structure

```
claude-agent-sdk-playground/
├── agent_builder/
│   ├── builder.py                  # Entry point: interactive chat loop
│   ├── identity/
│   │   ├── AGENT.md                # Builder's own operating manual
│   │   ├── SOUL.md                 # Builder's personality
│   │   └── MEMORY.md               # Tracks what agents have been built
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── scaffold.py             # @tool: create agent directory + boilerplate
│   │   ├── write_identity.py       # @tool: write AGENT.md, SOUL.md, MEMORY.md, USER.md
│   │   ├── write_tools.py          # @tool: write custom @tool functions
│   │   ├── test_agent.py           # @tool: run mock test of generated agent
│   │   └── registry.py             # @tool: register/list/describe agents
│   ├── templates/
│   │   ├── agent_main.py.tmpl      # Boilerplate: imports, main loop, message processing
│   │   └── env_example.tmpl        # .env.example template
│   ├── utils.py                    # Shared: build_claude_md() used by builder, agents, and tests
│   └── registry/
│       └── agents.json             # JSON registry of all created agents
├── output/                         # Generated agents land here
│   └── {agent_name}/
│       ├── agent.py                # Runnable entry point
│       ├── tools.py                # Custom @tool functions
│       ├── AGENT.md                # Operating manual (source)
│       ├── SOUL.md                 # Personality (source)
│       ├── MEMORY.md               # Persistent context (source)
│       ├── USER.md                 # (optional) User info (source)
│       ├── CLAUDE.md               # Auto-generated: combined identity (build artifact)
│       └── .env.example            # Required env vars
└── ...existing project files...
```

## Identity Files (OpenClaw-Inspired)

Each generated agent gets up to four identity files. Naming follows OpenClaw conventions.

| File | Purpose | Always created |
|------|---------|---------------|
| `AGENT.md` | Operating manual: purpose, available tools, rules, constraints, behavioral instructions | Yes |
| `SOUL.md` | Personality: tone, values, communication style, boundaries | Yes |
| `MEMORY.md` | Persistent context: initial knowledge seeded from the builder conversation | Yes |
| `USER.md` | User info: name, role, preferences — only if user provides this during builder conversation | No |

Identity files are kept separate for editing and version control, but at startup the agent combines them into a `CLAUDE.md` file which the SDK loads natively via `setting_sources=["project"]`.

**Startup flow:**
1. `build_claude_md()` reads AGENT.md + SOUL.md + MEMORY.md + USER.md (if it exists)
2. Concatenates them with section headers into a single `CLAUDE.md`
3. SDK loads `CLAUDE.md` automatically via `setting_sources=["project"]`
4. Agent is ready — no CLI args, no `append` hack, fully native SDK behavior

**Regeneration:** `build_claude_md()` runs at the start of **every session**, not just at build time. This means edits to any identity file (e.g., updating SOUL.md personality or adding context to MEMORY.md) are picked up on next launch without rebuilding.

**`CLAUDE.md` is a build artifact** — not hand-edited. The source of truth is always the four identity files. The generated `CLAUDE.md` includes a header comment:
```markdown
<!-- AUTO-GENERATED: Do not edit. Modify AGENT.md, SOUL.md, MEMORY.md, or USER.md instead. -->
```

**`build_claude_md()` (shared utility in `agent_builder/utils.py`):**
```python
def build_claude_md(source_dir: str, output_dir: str, verbose: bool = False) -> None
```
- Reads `AGENT.md`, `SOUL.md`, `MEMORY.md`, `USER.md` (if exists) from `source_dir`
- Concatenates with section headers (`# Agent`, `# Soul`, `# Memory`, `# User`)
- Prepends the auto-generated comment header
- Writes to `{output_dir}/CLAUDE.md`
- Logs file sizes if `verbose=True`
- Used by: `builder.py` (for builder identity), generated `agent.py` (for agent identity), `test_agent` tool (for test runs)
- Generated agents copy this function into their own directory at scaffold time so they're self-contained

This approach:
- Uses the SDK's intended mechanism for project context (`setting_sources`)
- Keeps identity files separate for easy editing (swap personality without touching instructions)
- Has no size limits
- No Windows CLI argument length issues — identity content never touches the command line
- Matches OpenClaw's pattern of bootstrapping from workspace files

## Builder Agent Configuration

```python
# Combine builder's own identity files into CLAUDE.md before starting
build_claude_md(
    source_dir="agent_builder/identity/",  # AGENT.md, SOUL.md, MEMORY.md
    output_dir="agent_builder/",           # writes CLAUDE.md here
)

ClaudeAgentOptions(
    # No system_prompt — SDK loads CLAUDE.md natively
    setting_sources=["project"],
    cwd="agent_builder/",
    mcp_servers={"builder_tools": builder_tools_server},
    allowed_tools=[
        "mcp__builder_tools__scaffold_agent",
        "mcp__builder_tools__write_identity",
        "mcp__builder_tools__write_tools",
        "mcp__builder_tools__test_agent",
        "mcp__builder_tools__registry",
        "Read", "Write", "Edit", "Glob", "Grep", "Bash",
    ],
    permission_mode="acceptEdits",
    max_turns=50,
    max_budget_usd=5.00,
)
```

**Key decisions:**
- **`setting_sources=["project"]`** loads `CLAUDE.md` from `cwd` natively. The builder's identity files (`agent_builder/identity/AGENT.md`, `SOUL.md`, `MEMORY.md`) are combined into `agent_builder/CLAUDE.md` at startup — same pattern as generated agents.
- **No subagents.** The earlier plan had `tool-designer` and `prompt-engineer` subagents, but the builder itself is Claude — it can design tools and write identity files directly in the main conversation without delegating. Subagents would add token cost (each gets a fresh context) and implementation complexity for no real benefit.
- **`acceptEdits`** auto-approves file writes. MCP tools are covered by `allowed_tools`. Bash commands that aren't filesystem ops may prompt, which is fine for safety.

## Builder Tools

Five custom `@tool` functions bundled into a single in-process MCP server via `create_sdk_mcp_server()`.

### `scaffold_agent`

**Purpose:** Create the agent directory and boilerplate files from templates.

**Input:** `{"agent_name": str, "description": str}`

**Behavior:**
1. Validates `agent_name` (alphanumeric + hyphens, no spaces)
2. Creates `output/{agent_name}/` directory
3. Renders `agent_main.py.tmpl` -> `output/{agent_name}/agent.py` with agent_name substituted
4. Renders `.env.example` from template
5. Returns confirmation with the created file paths

Note: `tools.py` is not created here — `write_tools` handles that as a complete file.

**Template zone:** Entire tool is deterministic.

### `write_identity`

**Purpose:** Write identity files with Claude-authored content.

**Input:**
```json
{
    "agent_name": str,
    "agent_md": str,
    "soul_md": str,
    "memory_md": str,
    "user_md": str | null
}
```

**Behavior:**
1. Writes each non-null string to its corresponding file in `output/{agent_name}/`
2. Returns confirmation with file paths and total character count

**Claude zone:** The content strings are authored by Claude in the conversation.

### `write_tools`

**Purpose:** Generate `tools.py` with custom `@tool` functions.

**Input:**
```json
{
    "agent_name": str,
    "tools_code": str
}
```

**Behavior:**
1. Prepends a template header containing standard imports (`from claude_agent_sdk import tool, create_sdk_mcp_server, ToolAnnotations`, `from typing import Any`) and the `TEST_MODE = False` declaration
2. Writes the `tools_code` string as-is after the header. This string is authored by Claude and must contain:
   - All `@tool` decorated functions (each with a `if TEST_MODE:` branch)
   - A `create_sdk_mcp_server()` call at the bottom that bundles all tool functions and assigns to `tools_server`
3. Writes the complete file to `output/{agent_name}/tools.py`
4. Returns confirmation

**Hybrid:** The import header and `TEST_MODE` declaration are template (deterministic). Everything else — tool functions, server creation, mock responses — is authored by Claude in `tools_code`.

### `test_agent`

**Purpose:** Run the generated agent in mock mode and verify it works.

**Input:**
```json
{
    "agent_name": str,
    "test_prompts": [str, str, str]
}
```

**Behavior:**
1. Reads `output/{agent_name}/tools.py` and replaces `TEST_MODE = False` with `TEST_MODE = True` (Python file I/O, not the SDK Edit tool — this runs inside a `@tool` handler)
2. Dynamically imports the generated `tools.py` using `importlib.util.spec_from_file_location()` + `module_from_spec()` to load `tools_server` from it at runtime
3. Calls `build_claude_md()` in the agent's output directory to generate `CLAUDE.md` from identity files
4. For each prompt, runs `query()` (one-shot, not ClaudeSDKClient) against the generated agent with:
   - `setting_sources=["project"]` to load the generated `CLAUDE.md` natively
   - `cwd` set to `output/{agent_name}/`
   - `mcp_servers={"agent_tools": tools_server}` from the dynamically imported module
   - `allowed_tools` matching `mcp__agent_tools__*` (wildcard covers all custom tools)
   - `max_turns=5` (test should be fast)
5. Collects results: checks for `ResultMessage.subtype == "success"` and no `AssistantMessage.error`
6. Resets `TEST_MODE = False` in `tools.py` (restores original)
7. Leaves `CLAUDE.md` in place so the user can run the agent immediately after building
8. Returns test results: which prompts passed/failed, error details for failures (including tracebacks)

**Template zone:** Test harness logic is deterministic. Test prompts are authored by Claude (contextual to the agent).

### `registry`

**Purpose:** Track all created agents.

**Input:**
```json
{
    "action": "add" | "list" | "describe",
    "agent_name": str | null,
    "description": str | null,
    "tools_list": [str] | null
}
```

**Behavior:**
- `add`: Appends entry to `registry/agents.json` with name, description, tools, creation date, output path, status
- `list`: Returns summary of all registered agents
- `describe`: Returns full details for one agent

**Template zone:** Entire tool is deterministic JSON read/write.

## Conversation Flow

### Phase 1 — Discovery

The builder asks one question at a time:
- What's the agent's purpose?
- What should it be called?
- What kind of tasks will it handle?
- Does it need to read/write files, run commands, or just talk?

### Phase 2 — Tool Design

Based on discovery, the builder proposes custom tools:
- "Based on what you described, I'd create these tools: `analyze_code`, `generate_report`. Sound good?"
- User can add, remove, or modify tools
- For each tool, the builder designs the input schema, description, and handler logic

### Phase 3 — Identity

The builder crafts the identity files freehand:
- `AGENT.md` — operating manual derived from the conversation
- `SOUL.md` — personality inferred from the use case and any stated preferences
- `MEMORY.md` — initial context seeded from what was discussed
- `USER.md` — only if user provided personal info

### Phase 4 — Generation

The builder calls its tools in sequence:
1. `scaffold_agent` — creates directory and boilerplate from templates
2. `write_identity` — writes the identity files
3. `write_tools` — generates `tools.py` with `@tool` functions including `TEST_MODE` branches
4. `registry` (action: "add") — registers the agent

### Phase 5 — Test & Self-Heal

1. Builder calls `test_agent` with 2-3 contextual test prompts
2. If all pass: shows mock responses, reports success
3. If any fail:
   - Builder reads the error traceback
   - Reads the generated `agent.py` and `tools.py` using its Read tool
   - Diagnoses the root cause in the conversation
   - Explains what went wrong to the user
   - Asks: "Want me to fix this?"
   - If yes: edits the generated files using Edit tool, re-runs test
   - Retries up to 3 times
   - After 3 failures: reports what's still broken, suggests manual fixes

### Phase 6 — Handoff

Builder prints: "Agent ready at `output/{name}/`. Run it with `python output/{name}/agent.py`"

## Generated Agent Configuration

Each generated agent uses `ClaudeSDKClient` for interactive multi-turn conversation.

```python
# build_claude_md() runs first, combining identity files into CLAUDE.md
build_claude_md()

ClaudeAgentOptions(
    # No system_prompt needed — SDK loads CLAUDE.md natively
    setting_sources=["project"],         # Loads CLAUDE.md from cwd
    cwd="output/{agent_name}/",          # Agent runs from its own directory
    mcp_servers={"agent_tools": tools_server},
    tools=[...],                         # Availability: which built-ins appear in context
    allowed_tools=[...],                 # Permission: which tools auto-approve
    permission_mode="...",               # Tiered based on use case
    hooks={
        "PreToolUse": [HookMatcher(matcher="Bash", hooks=[safety_hook])],
    },
    max_turns=25,
    max_budget_usd=1.00,
)
```

### Permission Tiers

The builder selects the appropriate tier during the discovery conversation:

| Tier | `tools=` | `allowed_tools=` | `permission_mode` | Use case |
|------|----------|-------------------|--------------------|----------|
| Read-only | `["Read", "Glob", "Grep"]` | `["Read", "Glob", "Grep"]` + MCP tools | `dontAsk` | Analysis, code review |
| Read-write | `["Read", "Edit", "Write", "Glob", "Grep"]` | Same + MCP tools | `acceptEdits` | Code generation, refactoring |
| Full automation | `["Read", "Edit", "Write", "Bash", "Glob", "Grep"]` | Same + MCP tools | `acceptEdits` | CI/CD, scripting, testing |

All tiers include a `PreToolUse` safety hook on Bash that blocks destructive patterns (`rm -rf /`, `DROP TABLE`, etc.).

### Mock Testing

Every generated `@tool` function includes a `TEST_MODE` branch:

```python
TEST_MODE = False

@tool("analyze_code", "Analyze code for issues", {"file_path": str})
async def analyze_code(args):
    if TEST_MODE:
        return {"content": [{"type": "text", "text": "Mock: Found 3 issues in main.py"}]}
    # Real implementation
    ...
```

The builder's `test_agent` tool flips `TEST_MODE = True` before running tests and resets it after. This ensures:
- No real file I/O, API calls, or side effects during testing
- Tools exercise the full `@tool` -> MCP server -> Claude -> response pipeline
- Mock responses are contextual (authored by Claude per tool)

### Debug / Verbose Mode

Both the builder and generated agents support a `--verbose` flag for development and troubleshooting.

**Activation:**
```bash
# Builder
python agent_builder/builder.py --verbose

# Generated agent
python output/my-agent/agent.py --verbose
```

**What verbose mode shows:**

| Normal mode | Verbose mode adds |
|-------------|-------------------|
| Assistant text | All message types (System, User, Assistant, Result) |
| Tool names | Tool inputs and full tool results |
| Errors | Full tracebacks and raw error objects |
| Final cost | Per-turn cost, token counts (input/output/cache), model name |
| — | Session ID, turn count, duration |
| — | MCP server connection status on startup |
| — | `CLAUDE.md` generation log (which identity files found, total size) |
| — | `SystemMessage` init data (available tools, settings loaded) |

**Implementation:** A `VERBOSE = False` flag in the template, set via `argparse` from CLI args. The message loop checks it:

```python
async for message in client.receive_response():
    if VERBOSE:
        print(f"[{message.__class__.__name__}] {message}")

    if isinstance(message, AssistantMessage):
        if message.error:
            print(f"[Error: {message.error}]")
            continue
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)
            elif isinstance(block, ToolUseBlock):
                if VERBOSE:
                    print(f"  [Tool: {block.name}] Input: {block.input}")
                else:
                    print(f"  [Tool: {block.name}]")
    elif isinstance(message, ResultMessage):
        if message.is_error:
            print(f"[Failed: {message.subtype}]")
        if VERBOSE:
            print(f"  [Session: {message.session_id}]")
            print(f"  [Turns: {message.num_turns}, Duration: {message.duration_ms}ms]")
            if message.usage:
                print(f"  [Tokens: in={message.usage.get('input_tokens', '?')} out={message.usage.get('output_tokens', '?')}]")
        if message.total_cost_usd:
            print(f"  [Cost: ${message.total_cost_usd:.4f}]")
    elif VERBOSE and isinstance(message, SystemMessage):
        if message.subtype == "init":
            print(f"  [Init: {message.data}]")
```

**For `build_claude_md()` in verbose mode:**
```
[build_claude_md] Found: AGENT.md (1204 chars), SOUL.md (856 chars), MEMORY.md (312 chars)
[build_claude_md] USER.md not found, skipping
[build_claude_md] Wrote CLAUDE.md (2452 chars total)
```

### Message Processing

Generated agents use the message loop shown above in verbose mode. In normal mode (default), the same loop but without the verbose branches — only assistant text, tool names, errors, and cost are shown.

## First Test Agent: "Codebase Navigator"

To validate the builder works, the first agent to build through it:

- **Purpose:** Navigate and explain any codebase
- **Name:** `codebase-navigator`
- **Tools:** One custom tool `summarize_file` that reads a file and explains what it does
- **Tier:** Read-only (`Read`, `Glob`, `Grep` + custom MCP tool)
- **Personality:** Patient teacher, explains at the right level, asks clarifying questions
- **Memory:** Empty initially, no pre-seeded knowledge
- **No write access** — safe for testing

## SDK Compliance

All API usage verified against the Claude Agent SDK Python documentation (docs/01-07):

- `query()` for one-shot test runs, `ClaudeSDKClient` for interactive sessions
- `@tool` decorator with `{"param": type}` input schemas
- `create_sdk_mcp_server()` to bundle tools
- MCP tool naming: `mcp__{server}__{tool}`
- `setting_sources=["project"]` with auto-generated `CLAUDE.md` for both the builder and generated agents — identity files are combined at startup via `build_claude_md()` and loaded natively by the SDK
- `tools=` (availability) and `allowed_tools=` (permission) used as distinct layers
- `HookMatcher` with `matcher=` regex and `hooks=` callback list
- Tool handlers return `{"content": [...], "is_error": True}` on failure, never throw
- `asyncio.to_thread(input, "> ")` for async-safe user input
- `max_turns` and `max_budget_usd` on all agents
- Error handling for `ResultMessage.is_error` and `AssistantMessage.error`
- Identity content loaded via `setting_sources=["project"]` + `CLAUDE.md`, never passed as CLI args
