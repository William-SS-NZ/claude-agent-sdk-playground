# Agent Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone interactive CLI meta-agent that creates purpose-built Claude Agent SDK agents through conversation, with mock testing and self-heal.

**Architecture:** Hybrid templates + Claude freehand. Templates handle boilerplate (agent.py main loop, imports). Claude writes tool handlers and identity files. Generated agents use `setting_sources=["project"]` with a `CLAUDE.md` built from identity files at startup.

**Tech Stack:** Python 3.10+, claude-agent-sdk, anyio, argparse, json, pathlib, importlib, re

**Spec:** `docs/superpowers/specs/2026-04-13-agent-builder-design.md`

---

## File Structure

```
agent_builder/
├── builder.py                      # Entry point: argparse + ClaudeSDKClient chat loop
├── utils.py                        # build_claude_md() shared utility
├── identity/
│   ├── AGENT.md                    # Builder's operating manual
│   ├── SOUL.md                     # Builder's personality
│   └── MEMORY.md                   # Builder's initial context
├── tools/
│   ├── __init__.py                 # Imports all tools, creates builder_tools_server
│   ├── scaffold.py                 # scaffold_agent tool
│   ├── write_identity.py           # write_identity tool
│   ├── write_tools.py              # write_tools tool
│   ├── test_agent.py               # test_agent tool
│   └── registry.py                 # registry tool
├── templates/
│   ├── agent_main.py.tmpl          # Generated agent.py template
│   └── env_example.tmpl            # Generated .env.example template
└── registry/
    └── agents.json                 # Agent registry (starts as empty array)
output/                             # Generated agents land here (gitignored)
tests/
├── test_utils.py                   # Tests for build_claude_md
├── test_scaffold.py                # Tests for scaffold_agent tool
├── test_write_identity.py          # Tests for write_identity tool
├── test_write_tools.py             # Tests for write_tools tool
├── test_registry.py                # Tests for registry tool
└── conftest.py                     # Shared fixtures (tmp dirs, sample data)
```

Each builder tool is one file, one responsibility. The `__init__.py` bundles them into the MCP server. Tests mirror the tool structure.

---

### Task 1: Project Setup and Shared Utility

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `agent_builder/__init__.py`
- Create: `agent_builder/utils.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_utils.py`

- [ ] **Step 1: Update pyproject.toml with test dependencies**

```toml
[project]
name = "claude-agent-sdk-playground"
version = "0.1.0"
description = "Agent Builder — create purpose-built Claude Agent SDK agents through conversation"
requires-python = ">=3.10"
dependencies = [
    "claude-agent-sdk",
    "anyio",
]

[project.optional-dependencies]
dev = [
    "python-dotenv",
    "pytest",
    "pytest-asyncio",
]
```

- [ ] **Step 2: Update .gitignore to exclude output directory**

Append to `.gitignore`:
```
# Generated agents
output/

# Build artifacts
agent_builder/CLAUDE.md
```

- [ ] **Step 3: Create agent_builder package init**

Create `agent_builder/__init__.py`:
```python
"""Agent Builder — create purpose-built Claude Agent SDK agents through conversation."""
```

- [ ] **Step 4: Write the failing test for build_claude_md**

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:
```python
import pytest
from pathlib import Path


@pytest.fixture
def tmp_agent_dir(tmp_path: Path) -> Path:
    """Create a temporary agent directory with sample identity files."""
    identity_dir = tmp_path / "identity"
    identity_dir.mkdir()

    (identity_dir / "AGENT.md").write_text("# Agent\nYou are a test agent.", encoding="utf-8")
    (identity_dir / "SOUL.md").write_text("# Soul\nBe helpful and concise.", encoding="utf-8")
    (identity_dir / "MEMORY.md").write_text("# Memory\nNo prior context.", encoding="utf-8")

    return tmp_path


@pytest.fixture
def tmp_agent_dir_with_user(tmp_agent_dir: Path) -> Path:
    """Same as tmp_agent_dir but includes USER.md."""
    identity_dir = tmp_agent_dir / "identity"
    (identity_dir / "USER.md").write_text("# User\nName: William", encoding="utf-8")
    return tmp_agent_dir
```

Create `tests/test_utils.py`:
```python
import pytest
from pathlib import Path
from agent_builder.utils import build_claude_md


def test_build_claude_md_creates_file(tmp_agent_dir: Path):
    source = str(tmp_agent_dir / "identity")
    output = str(tmp_agent_dir)

    build_claude_md(source_dir=source, output_dir=output)

    claude_md = tmp_agent_dir / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in content
    assert "# Agent" in content
    assert "You are a test agent." in content
    assert "# Soul" in content
    assert "Be helpful and concise." in content
    assert "# Memory" in content
    assert "No prior context." in content


def test_build_claude_md_skips_missing_user_md(tmp_agent_dir: Path):
    source = str(tmp_agent_dir / "identity")
    output = str(tmp_agent_dir)

    build_claude_md(source_dir=source, output_dir=output)

    content = (tmp_agent_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# User" not in content


def test_build_claude_md_includes_user_md_when_present(tmp_agent_dir_with_user: Path):
    source = str(tmp_agent_dir_with_user / "identity")
    output = str(tmp_agent_dir_with_user)

    build_claude_md(source_dir=source, output_dir=output)

    content = (tmp_agent_dir_with_user / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# User" in content
    assert "Name: William" in content


def test_build_claude_md_verbose_output(tmp_agent_dir: Path, capsys: pytest.CaptureFixture[str]):
    source = str(tmp_agent_dir / "identity")
    output = str(tmp_agent_dir)

    build_claude_md(source_dir=source, output_dir=output, verbose=True)

    captured = capsys.readouterr()
    assert "[build_claude_md] Found:" in captured.out
    assert "AGENT.md" in captured.out
    assert "Wrote CLAUDE.md" in captured.out


def test_build_claude_md_overwrites_existing(tmp_agent_dir: Path):
    output = str(tmp_agent_dir)
    claude_md = tmp_agent_dir / "CLAUDE.md"
    claude_md.write_text("old content", encoding="utf-8")

    build_claude_md(source_dir=str(tmp_agent_dir / "identity"), output_dir=output)

    content = claude_md.read_text(encoding="utf-8")
    assert "old content" not in content
    assert "AUTO-GENERATED" in content
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `python -m pytest tests/test_utils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_builder.utils'`

- [ ] **Step 6: Implement build_claude_md**

Create `agent_builder/utils.py`:
```python
"""Shared utilities for the Agent Builder."""

from pathlib import Path

CLAUDE_MD_HEADER = "<!-- AUTO-GENERATED: Do not edit. Modify AGENT.md, SOUL.md, MEMORY.md, or USER.md instead. -->\n\n"

IDENTITY_FILES = [
    ("AGENT.md", "# Agent"),
    ("SOUL.md", "# Soul"),
    ("MEMORY.md", "# Memory"),
    ("USER.md", "# User"),
]


def build_claude_md(source_dir: str, output_dir: str, verbose: bool = False) -> None:
    """Combine identity files into a single CLAUDE.md for SDK loading.

    Reads AGENT.md, SOUL.md, MEMORY.md, and USER.md (if exists) from source_dir,
    concatenates them with section headers, and writes CLAUDE.md to output_dir.

    Args:
        source_dir: Directory containing identity files.
        output_dir: Directory to write CLAUDE.md to.
        verbose: If True, print file sizes and progress.
    """
    source = Path(source_dir)
    output = Path(output_dir)
    sections: list[str] = []
    found_files: list[str] = []

    for filename, _header in IDENTITY_FILES:
        filepath = source / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            sections.append(content)
            if verbose:
                found_files.append(f"{filename} ({len(content)} chars)")
        elif filename == "USER.md":
            if verbose:
                print(f"[build_claude_md] {filename} not found, skipping")
        else:
            raise FileNotFoundError(f"Required identity file not found: {filepath}")

    combined = CLAUDE_MD_HEADER + "\n\n---\n\n".join(sections)
    output_path = output / "CLAUDE.md"
    output_path.write_text(combined, encoding="utf-8")

    if verbose:
        print(f"[build_claude_md] Found: {', '.join(found_files)}")
        print(f"[build_claude_md] Wrote CLAUDE.md ({len(combined)} chars total)")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_utils.py -v`
Expected: All 5 tests PASS

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore agent_builder/__init__.py agent_builder/utils.py tests/
git commit -m "feat: add build_claude_md utility and project setup"
```

---

### Task 2: Agent Main Template

**Files:**
- Create: `agent_builder/templates/agent_main.py.tmpl`
- Create: `agent_builder/templates/env_example.tmpl`

- [ ] **Step 1: Create the agent_main.py template**

Create `agent_builder/templates/agent_main.py.tmpl`:
```python
"""{{agent_name}} — generated by Agent Builder."""

import asyncio
import argparse
from pathlib import Path

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    HookMatcher,
)

AGENT_NAME = "{{agent_name}}"
AGENT_DIR = Path(__file__).parent.resolve()

# --- Identity bootstrap ---

CLAUDE_MD_HEADER = "<!-- AUTO-GENERATED: Do not edit. Modify AGENT.md, SOUL.md, MEMORY.md, or USER.md instead. -->\n\n"

IDENTITY_FILES = [
    ("AGENT.md", "# Agent"),
    ("SOUL.md", "# Soul"),
    ("MEMORY.md", "# Memory"),
    ("USER.md", "# User"),
]


def build_claude_md(verbose: bool = False) -> None:
    """Combine identity files into CLAUDE.md for SDK loading."""
    sections: list[str] = []
    found_files: list[str] = []

    for filename, _header in IDENTITY_FILES:
        filepath = AGENT_DIR / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            sections.append(content)
            if verbose:
                found_files.append(f"{filename} ({len(content)} chars)")
        elif filename == "USER.md":
            if verbose:
                print(f"[build_claude_md] {filename} not found, skipping")

    combined = CLAUDE_MD_HEADER + "\n\n---\n\n".join(sections)
    output_path = AGENT_DIR / "CLAUDE.md"
    output_path.write_text(combined, encoding="utf-8")

    if verbose:
        print(f"[build_claude_md] Found: {', '.join(found_files)}")
        print(f"[build_claude_md] Wrote CLAUDE.md ({len(combined)} chars total)")


# --- Safety hook ---

async def safety_hook(input_data, tool_use_id, context):
    """Block common destructive bash patterns."""
    if input_data["tool_name"] == "Bash":
        command = input_data["tool_input"].get("command", "")
        blocked = ["rm -rf /", "DROP TABLE", "DELETE FROM", "> /dev/sda"]
        for pattern in blocked:
            if pattern in command:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Blocked dangerous pattern: {pattern}",
                    }
                }
    return {}


# --- Main ---

async def main():
    parser = argparse.ArgumentParser(description=f"{AGENT_NAME} agent")
    parser.add_argument("--verbose", action="store_true", help="Show debug output")
    args = parser.parse_args()
    verbose = args.verbose

    build_claude_md(verbose=verbose)

    from tools import tools_server  # noqa: E402

    options = ClaudeAgentOptions(
        setting_sources=["project"],
        cwd=str(AGENT_DIR),
        mcp_servers={"agent_tools": tools_server},
        tools={{tools_list}},
        allowed_tools={{allowed_tools_list}},
        permission_mode="{{permission_mode}}",
        hooks={
            "PreToolUse": [HookMatcher(matcher="Bash", hooks=[safety_hook])],
        },
        max_turns=25,
        max_budget_usd=1.00,
    )

    async with ClaudeSDKClient(options=options) as client:
        print(f"\n  {AGENT_NAME} ready. Type 'exit' to quit.\n")

        while True:
            user_input = await asyncio.to_thread(input, "> ")
            if user_input.strip().lower() in ("exit", "quit"):
                break

            await client.query(user_input)
            async for message in client.receive_response():
                if verbose:
                    print(f"[{message.__class__.__name__}] {message}")

                if isinstance(message, AssistantMessage):
                    if message.error:
                        print(f"[Error: {message.error}]")
                        continue
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text)
                        elif isinstance(block, ToolUseBlock):
                            if verbose:
                                print(f"  [Tool: {block.name}] Input: {block.input}")
                            else:
                                print(f"  [Tool: {block.name}]")
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        print(f"[Failed: {message.subtype}]")
                    if verbose:
                        print(f"  [Session: {message.session_id}]")
                        print(f"  [Turns: {message.num_turns}, Duration: {message.duration_ms}ms]")
                        if message.usage:
                            print(f"  [Tokens: in={message.usage.get('input_tokens', '?')} out={message.usage.get('output_tokens', '?')}]")
                    if message.total_cost_usd:
                        print(f"  [Cost: ${message.total_cost_usd:.4f}]")
                elif verbose and isinstance(message, SystemMessage):
                    if message.subtype == "init":
                        print(f"  [Init: {message.data}]")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Create the .env.example template**

Create `agent_builder/templates/env_example.tmpl`:
```
# Copy this to .env and fill in your API key
ANTHROPIC_API_KEY=your-api-key-here
```

- [ ] **Step 3: Commit**

```bash
git add agent_builder/templates/
git commit -m "feat: add agent_main.py and env_example templates"
```

---

### Task 3: scaffold_agent Tool

**Files:**
- Create: `agent_builder/tools/__init__.py`
- Create: `agent_builder/tools/scaffold.py`
- Create: `tests/test_scaffold.py`

- [ ] **Step 1: Write failing tests for scaffold_agent**

Create `tests/test_scaffold.py`:
```python
import pytest
import json
from pathlib import Path
from agent_builder.tools.scaffold import scaffold_agent


@pytest.mark.asyncio
async def test_scaffold_creates_directory_and_files(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "test-agent", "description": "A test agent"},
        output_base=str(tmp_path),
    )
    content = result["content"][0]["text"]
    agent_dir = tmp_path / "test-agent"

    assert agent_dir.exists()
    assert (agent_dir / "agent.py").exists()
    assert (agent_dir / ".env.example").exists()
    assert (agent_dir / ".gitignore").exists()
    assert "test-agent" in (agent_dir / "agent.py").read_text(encoding="utf-8")
    assert "Created" in content


@pytest.mark.asyncio
async def test_scaffold_rejects_invalid_name(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "../escape", "description": "bad"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True
    assert "Invalid" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_scaffold_rejects_dotdot_in_name(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "foo..bar", "description": "bad"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_scaffold_rejects_uppercase(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "MyAgent", "description": "bad"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_scaffold_rejects_existing_directory(tmp_path: Path):
    (tmp_path / "existing-agent").mkdir()
    result = await scaffold_agent(
        {"agent_name": "existing-agent", "description": "dup"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True
    assert "exists" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_scaffold_gitignore_contents(tmp_path: Path):
    await scaffold_agent(
        {"agent_name": "test-agent", "description": "test"},
        output_base=str(tmp_path),
    )
    gitignore = (tmp_path / "test-agent" / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "__pycache__" in gitignore
    assert "CLAUDE.md" in gitignore
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scaffold.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement scaffold_agent**

Create `agent_builder/tools/__init__.py`:
```python
"""Builder tools — bundled into a single MCP server."""
```

Create `agent_builder/tools/scaffold.py`:
```python
"""scaffold_agent tool — creates agent directory and boilerplate files."""

import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

GITIGNORE_CONTENT = """\
.env
.env.local
__pycache__/
*.py[cod]
CLAUDE.md
"""


def _validate_agent_name(agent_name: str, output_base: str) -> str | None:
    """Validate agent_name and return error message if invalid, None if valid."""
    if not NAME_PATTERN.match(agent_name):
        return f"Invalid agent name '{agent_name}'. Must match ^[a-z0-9][a-z0-9-]*$ (lowercase alphanumeric and hyphens, must start with alphanumeric)."

    if ".." in agent_name or "/" in agent_name or "\\" in agent_name:
        return f"Invalid agent name '{agent_name}'. Must not contain '..', '/', or '\\\\'."

    resolved = (Path(output_base) / agent_name).resolve()
    base_resolved = Path(output_base).resolve()
    if not str(resolved).startswith(str(base_resolved)):
        return f"Invalid agent name '{agent_name}'. Path traversal detected."

    return None


@tool(
    "scaffold_agent",
    "Create the directory structure and boilerplate files for a new agent",
    {"agent_name": str, "description": str},
)
async def scaffold_agent(args: dict[str, Any], output_base: str = "output") -> dict[str, Any]:
    agent_name = args["agent_name"]
    description = args["description"]

    error = _validate_agent_name(agent_name, output_base)
    if error:
        return {"content": [{"type": "text", "text": error}], "is_error": True}

    agent_dir = Path(output_base) / agent_name

    if agent_dir.exists():
        return {
            "content": [{"type": "text", "text": f"Directory already exists: {agent_dir}"}],
            "is_error": True,
        }

    agent_dir.mkdir(parents=True)

    # Render agent_main.py template
    template_path = TEMPLATES_DIR / "agent_main.py.tmpl"
    template = template_path.read_text(encoding="utf-8")
    agent_py = template.replace("{{agent_name}}", agent_name)
    (agent_dir / "agent.py").write_text(agent_py, encoding="utf-8")

    # Render .env.example
    env_template_path = TEMPLATES_DIR / "env_example.tmpl"
    env_content = env_template_path.read_text(encoding="utf-8")
    (agent_dir / ".env.example").write_text(env_content, encoding="utf-8")

    # Write .gitignore
    (agent_dir / ".gitignore").write_text(GITIGNORE_CONTENT, encoding="utf-8")

    created_files = ["agent.py", ".env.example", ".gitignore"]
    return {
        "content": [
            {
                "type": "text",
                "text": f"Created agent '{agent_name}' at {agent_dir}/\nFiles: {', '.join(created_files)}\nDescription: {description}",
            }
        ]
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scaffold.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/ tests/test_scaffold.py
git commit -m "feat: add scaffold_agent tool with path traversal guard"
```

---

### Task 4: write_identity Tool

**Files:**
- Create: `agent_builder/tools/write_identity.py`
- Create: `tests/test_write_identity.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_write_identity.py`:
```python
import pytest
from pathlib import Path
from agent_builder.tools.write_identity import write_identity


@pytest.mark.asyncio
async def test_writes_all_identity_files(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    result = await write_identity({
        "agent_name": "test-agent",
        "agent_md": "# Agent\nYou review code.",
        "soul_md": "# Soul\nBe thorough.",
        "memory_md": "# Memory\nNo context yet.",
        "user_md": None,
    }, output_base=str(tmp_path))

    assert (agent_dir / "AGENT.md").read_text(encoding="utf-8") == "# Agent\nYou review code."
    assert (agent_dir / "SOUL.md").read_text(encoding="utf-8") == "# Soul\nBe thorough."
    assert (agent_dir / "MEMORY.md").read_text(encoding="utf-8") == "# Memory\nNo context yet."
    assert not (agent_dir / "USER.md").exists()
    assert "is_error" not in result


@pytest.mark.asyncio
async def test_writes_user_md_when_provided(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    await write_identity({
        "agent_name": "test-agent",
        "agent_md": "# Agent",
        "soul_md": "# Soul",
        "memory_md": "# Memory",
        "user_md": "# User\nName: William",
    }, output_base=str(tmp_path))

    assert (agent_dir / "USER.md").read_text(encoding="utf-8") == "# User\nName: William"


@pytest.mark.asyncio
async def test_reports_char_count(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    result = await write_identity({
        "agent_name": "test-agent",
        "agent_md": "A" * 100,
        "soul_md": "B" * 200,
        "memory_md": "C" * 50,
        "user_md": None,
    }, output_base=str(tmp_path))

    text = result["content"][0]["text"]
    assert "350" in text  # total chars


@pytest.mark.asyncio
async def test_errors_on_missing_directory(tmp_path: Path):
    result = await write_identity({
        "agent_name": "nonexistent",
        "agent_md": "# Agent",
        "soul_md": "# Soul",
        "memory_md": "# Memory",
        "user_md": None,
    }, output_base=str(tmp_path))

    assert result.get("is_error") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_write_identity.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement write_identity**

Create `agent_builder/tools/write_identity.py`:
```python
"""write_identity tool — writes AGENT.md, SOUL.md, MEMORY.md, USER.md."""

from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

FILE_MAP = {
    "agent_md": "AGENT.md",
    "soul_md": "SOUL.md",
    "memory_md": "MEMORY.md",
    "user_md": "USER.md",
}


@tool(
    "write_identity",
    "Write identity files (AGENT.md, SOUL.md, MEMORY.md, USER.md) for a generated agent",
    {
        "agent_name": str,
        "agent_md": str,
        "soul_md": str,
        "memory_md": str,
    },
)
async def write_identity(args: dict[str, Any], output_base: str = "output") -> dict[str, Any]:
    agent_name = args["agent_name"]
    agent_dir = Path(output_base) / agent_name

    if not agent_dir.exists():
        return {
            "content": [{"type": "text", "text": f"Agent directory not found: {agent_dir}"}],
            "is_error": True,
        }

    written: list[str] = []
    total_chars = 0

    for key, filename in FILE_MAP.items():
        content = args.get(key)
        if content is None:
            continue
        (agent_dir / filename).write_text(content, encoding="utf-8")
        written.append(filename)
        total_chars += len(content)

    return {
        "content": [
            {
                "type": "text",
                "text": f"Wrote identity files for '{agent_name}': {', '.join(written)} ({total_chars} chars total)",
            }
        ]
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_write_identity.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/write_identity.py tests/test_write_identity.py
git commit -m "feat: add write_identity tool"
```

---

### Task 5: write_tools Tool

**Files:**
- Create: `agent_builder/tools/write_tools.py`
- Create: `tests/test_write_tools.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_write_tools.py`:
```python
import pytest
from pathlib import Path
from agent_builder.tools.write_tools import write_tools

SAMPLE_TOOLS_CODE = '''
@tool("greet", "Greet a user", {"name": str})
async def greet(args: dict[str, Any]) -> dict[str, Any]:
    if TEST_MODE:
        return {"content": [{"type": "text", "text": "Mock: Hello, friend!"}]}
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}


tools_server = create_sdk_mcp_server(name="agent-tools", version="1.0.0", tools=[greet])
'''


@pytest.mark.asyncio
async def test_write_tools_creates_file(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    result = await write_tools(
        {"agent_name": "test-agent", "tools_code": SAMPLE_TOOLS_CODE},
        output_base=str(tmp_path),
    )

    tools_py = agent_dir / "tools.py"
    assert tools_py.exists()
    content = tools_py.read_text(encoding="utf-8")
    assert "TEST_MODE = False" in content
    assert "from claude_agent_sdk import" in content
    assert "from typing import Any" in content
    assert "async def greet" in content
    assert "tools_server" in content
    assert "is_error" not in result


@pytest.mark.asyncio
async def test_write_tools_header_before_code(tmp_path: Path):
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    await write_tools(
        {"agent_name": "test-agent", "tools_code": SAMPLE_TOOLS_CODE},
        output_base=str(tmp_path),
    )

    content = (agent_dir / "tools.py").read_text(encoding="utf-8")
    header_pos = content.index("TEST_MODE = False")
    code_pos = content.index("async def greet")
    assert header_pos < code_pos


@pytest.mark.asyncio
async def test_write_tools_errors_on_missing_dir(tmp_path: Path):
    result = await write_tools(
        {"agent_name": "nonexistent", "tools_code": SAMPLE_TOOLS_CODE},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_write_tools.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement write_tools**

Create `agent_builder/tools/write_tools.py`:
```python
"""write_tools tool — generates tools.py with custom @tool functions."""

from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

TOOLS_HEADER = '''\
"""Custom tools for this agent — generated by Agent Builder."""

from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server, ToolAnnotations

TEST_MODE = False
'''


@tool(
    "write_tools",
    "Generate tools.py with custom @tool functions for a generated agent. "
    "tools_code must contain all @tool decorated functions (each with an if TEST_MODE: branch) "
    "and a create_sdk_mcp_server() call at the bottom assigning to tools_server.",
    {"agent_name": str, "tools_code": str},
)
async def write_tools(args: dict[str, Any], output_base: str = "output") -> dict[str, Any]:
    agent_name = args["agent_name"]
    tools_code = args["tools_code"]
    agent_dir = Path(output_base) / agent_name

    if not agent_dir.exists():
        return {
            "content": [{"type": "text", "text": f"Agent directory not found: {agent_dir}"}],
            "is_error": True,
        }

    full_content = TOOLS_HEADER + "\n" + tools_code
    (agent_dir / "tools.py").write_text(full_content, encoding="utf-8")

    return {
        "content": [
            {
                "type": "text",
                "text": f"Wrote tools.py for '{agent_name}' ({len(full_content)} chars)",
            }
        ]
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_write_tools.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/write_tools.py tests/test_write_tools.py
git commit -m "feat: add write_tools tool"
```

---

### Task 6: registry Tool

**Files:**
- Create: `agent_builder/tools/registry.py`
- Create: `agent_builder/registry/agents.json`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_registry.py`:
```python
import pytest
import json
from pathlib import Path
from agent_builder.tools.registry import registry


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    path = tmp_path / "agents.json"
    path.write_text("[]", encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_add_agent(registry_path: Path):
    result = await registry({
        "action": "add",
        "agent_name": "test-agent",
        "description": "A test agent",
        "tools_list": ["greet", "farewell"],
    }, registry_file=str(registry_path))

    assert "is_error" not in result
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["name"] == "test-agent"
    assert data[0]["description"] == "A test agent"
    assert data[0]["tools"] == ["greet", "farewell"]
    assert "created" in data[0]
    assert data[0]["status"] == "active"


@pytest.mark.asyncio
async def test_list_agents(registry_path: Path):
    await registry({
        "action": "add",
        "agent_name": "agent-a",
        "description": "First",
        "tools_list": ["tool1"],
    }, registry_file=str(registry_path))
    await registry({
        "action": "add",
        "agent_name": "agent-b",
        "description": "Second",
        "tools_list": ["tool2"],
    }, registry_file=str(registry_path))

    result = await registry({"action": "list"}, registry_file=str(registry_path))
    text = result["content"][0]["text"]
    assert "agent-a" in text
    assert "agent-b" in text


@pytest.mark.asyncio
async def test_describe_agent(registry_path: Path):
    await registry({
        "action": "add",
        "agent_name": "my-agent",
        "description": "Does things",
        "tools_list": ["analyze"],
    }, registry_file=str(registry_path))

    result = await registry({
        "action": "describe",
        "agent_name": "my-agent",
    }, registry_file=str(registry_path))

    text = result["content"][0]["text"]
    assert "my-agent" in text
    assert "Does things" in text
    assert "analyze" in text


@pytest.mark.asyncio
async def test_describe_missing_agent(registry_path: Path):
    result = await registry({
        "action": "describe",
        "agent_name": "nonexistent",
    }, registry_file=str(registry_path))
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_list_empty_registry(registry_path: Path):
    result = await registry({"action": "list"}, registry_file=str(registry_path))
    text = result["content"][0]["text"]
    assert "No agents" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement registry**

Create `agent_builder/registry/agents.json`:
```json
[]
```

Create `agent_builder/tools/registry.py`:
```python
"""registry tool — track created agents in agents.json."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

DEFAULT_REGISTRY = str(Path(__file__).parent.parent / "registry" / "agents.json")


@tool(
    "registry",
    "Manage the agent registry. Actions: 'add' (register new agent), 'list' (show all agents), 'describe' (show details for one agent).",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "describe"]},
            "agent_name": {"type": "string"},
            "description": {"type": "string"},
            "tools_list": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action"],
    },
)
async def registry(args: dict[str, Any], registry_file: str = DEFAULT_REGISTRY) -> dict[str, Any]:
    path = Path(registry_file)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")

    agents: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    action = args["action"]

    if action == "add":
        agent_name = args.get("agent_name", "")
        entry = {
            "name": agent_name,
            "description": args.get("description", ""),
            "tools": args.get("tools_list", []),
            "created": date.today().isoformat(),
            "path": f"output/{agent_name}/",
            "status": "active",
        }
        agents.append(entry)
        path.write_text(json.dumps(agents, indent=2), encoding="utf-8")
        return {
            "content": [{"type": "text", "text": f"Registered agent '{agent_name}' in registry."}]
        }

    if action == "list":
        if not agents:
            return {"content": [{"type": "text", "text": "No agents registered yet."}]}
        lines = [f"- **{a['name']}**: {a['description']} ({len(a['tools'])} tools, {a['status']})" for a in agents]
        return {"content": [{"type": "text", "text": "Registered agents:\n" + "\n".join(lines)}]}

    if action == "describe":
        agent_name = args.get("agent_name", "")
        match = next((a for a in agents if a["name"] == agent_name), None)
        if not match:
            return {
                "content": [{"type": "text", "text": f"Agent '{agent_name}' not found in registry."}],
                "is_error": True,
            }
        details = json.dumps(match, indent=2)
        return {"content": [{"type": "text", "text": f"Agent details:\n{details}"}]}

    return {
        "content": [{"type": "text", "text": f"Unknown action: {action}"}],
        "is_error": True,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_registry.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent_builder/tools/registry.py agent_builder/registry/agents.json tests/test_registry.py
git commit -m "feat: add registry tool for tracking created agents"
```

---

### Task 7: test_agent Tool

**Files:**
- Create: `agent_builder/tools/test_agent.py`

Note: This tool calls `query()` from the SDK which requires an API key and running Claude. We won't write automated tests for it — it will be validated during the end-to-end smoke test in Task 9.

- [ ] **Step 1: Implement test_agent**

Create `agent_builder/tools/test_agent.py`:
```python
"""test_agent tool — run generated agent in mock mode and verify it works."""

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    tool,
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
)
from agent_builder.utils import build_claude_md


def _set_test_mode(tools_py_path: Path, enabled: bool) -> None:
    """Flip TEST_MODE in a tools.py file."""
    content = tools_py_path.read_text(encoding="utf-8")
    if enabled:
        content = content.replace("TEST_MODE = False", "TEST_MODE = True")
    else:
        content = content.replace("TEST_MODE = True", "TEST_MODE = False")
    tools_py_path.write_text(content, encoding="utf-8")


def _load_tools_server(tools_py_path: Path) -> Any:
    """Dynamically import tools.py and return the tools_server object."""
    spec = importlib.util.spec_from_file_location("generated_tools", str(tools_py_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {tools_py_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generated_tools"] = module
    spec.loader.exec_module(module)
    return module.tools_server


@tool(
    "test_agent",
    "Run a generated agent in mock mode (TEST_MODE=True) to verify it works. "
    "Sends test prompts and reports pass/fail for each.",
    {"agent_name": str, "test_prompts": list},
)
async def test_agent(args: dict[str, Any], output_base: str = "output") -> dict[str, Any]:
    agent_name = args["agent_name"]
    test_prompts: list[str] = args["test_prompts"]
    agent_dir = Path(output_base) / agent_name
    tools_py_path = agent_dir / "tools.py"

    if not tools_py_path.exists():
        return {
            "content": [{"type": "text", "text": f"tools.py not found at {tools_py_path}"}],
            "is_error": True,
        }

    # Build CLAUDE.md from identity files
    identity_dir = str(agent_dir)
    try:
        build_claude_md(source_dir=identity_dir, output_dir=identity_dir)
    except FileNotFoundError as e:
        return {
            "content": [{"type": "text", "text": f"Identity file missing: {e}"}],
            "is_error": True,
        }

    # Flip TEST_MODE and load tools
    _set_test_mode(tools_py_path, enabled=True)
    try:
        try:
            tools_server = _load_tools_server(tools_py_path)
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Failed to import tools.py:\n{traceback.format_exc()}",
                    }
                ],
                "is_error": True,
            }

        options = ClaudeAgentOptions(
            setting_sources=["project"],
            cwd=str(agent_dir),
            mcp_servers={"agent_tools": tools_server},
            allowed_tools=["mcp__agent_tools__*"],
            max_turns=5,
        )

        results: list[dict[str, str]] = []
        for prompt in test_prompts:
            try:
                status = "fail"
                error_detail = ""
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, AssistantMessage) and message.error:
                        error_detail = str(message.error)
                    if isinstance(message, ResultMessage):
                        if message.subtype == "success":
                            status = "pass"
                        else:
                            error_detail = f"subtype={message.subtype}"
                results.append({"prompt": prompt, "status": status, "error": error_detail})
            except Exception as e:
                results.append({"prompt": prompt, "status": "fail", "error": str(e)})

    finally:
        # Always reset TEST_MODE
        _set_test_mode(tools_py_path, enabled=False)
        # Clean up sys.modules
        sys.modules.pop("generated_tools", None)

    passed = sum(1 for r in results if r["status"] == "pass")
    total = len(results)
    lines = [f"Test results for '{agent_name}': {passed}/{total} passed\n"]
    for r in results:
        icon = "PASS" if r["status"] == "pass" else "FAIL"
        line = f"  [{icon}] {r['prompt']}"
        if r["error"]:
            line += f"\n         Error: {r['error']}"
        lines.append(line)

    all_passed = passed == total
    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "is_error": not all_passed,
    }
```

- [ ] **Step 2: Commit**

```bash
git add agent_builder/tools/test_agent.py
git commit -m "feat: add test_agent tool with try/finally TEST_MODE guard"
```

---

### Task 8: Bundle Tools into MCP Server + Builder Identity + Builder Entry Point

**Files:**
- Modify: `agent_builder/tools/__init__.py`
- Create: `agent_builder/identity/AGENT.md`
- Create: `agent_builder/identity/SOUL.md`
- Create: `agent_builder/identity/MEMORY.md`
- Create: `agent_builder/builder.py`

- [ ] **Step 1: Bundle all tools into MCP server**

Update `agent_builder/tools/__init__.py`:
```python
"""Builder tools — bundled into a single MCP server."""

from claude_agent_sdk import create_sdk_mcp_server

from agent_builder.tools.scaffold import scaffold_agent
from agent_builder.tools.write_identity import write_identity
from agent_builder.tools.write_tools import write_tools
from agent_builder.tools.test_agent import test_agent
from agent_builder.tools.registry import registry

builder_tools_server = create_sdk_mcp_server(
    name="builder_tools",
    version="1.0.0",
    tools=[scaffold_agent, write_identity, write_tools, test_agent, registry],
)
```

- [ ] **Step 2: Create builder identity files**

Create `agent_builder/identity/AGENT.md`:
```markdown
# Agent Builder — Operating Manual

You are the Agent Builder. You create purpose-built Claude Agent SDK agents through interactive conversation.

## Your Workflow

Follow these phases in order:

### Phase 1: Discovery
Ask one question at a time to understand:
- What is the agent's purpose?
- What should it be called? (lowercase, hyphens only, e.g. "code-reviewer")
- What kind of tasks will it handle?
- Does it need to read/write files, run commands, or just talk?

### Phase 2: Tool Design
Based on discovery, propose custom tools:
- Name each tool, describe what it does, define its input schema
- Each tool MUST include a `if TEST_MODE:` branch returning mock data
- Each tool MUST return `{"content": [{"type": "text", "text": "..."}]}`
- On errors, return `is_error: True` instead of raising exceptions

### Phase 3: Identity
Craft identity files for the agent:
- AGENT.md: operating manual — purpose, tools, rules, constraints
- SOUL.md: personality — tone, values, communication style
- MEMORY.md: initial context seeded from the conversation
- USER.md: only if the user shares personal info

### Phase 4: Generation
Call your tools in this exact sequence:
1. `scaffold_agent` with the agent name and description
2. `write_identity` with all identity file content
3. `write_tools` with the complete tools code including `create_sdk_mcp_server()` call
4. `registry` with action "add"

### Phase 5: Test
1. Call `test_agent` with 2-3 prompts relevant to the agent's purpose
2. If tests fail: read the error, diagnose it, explain to the user, ask if they want you to fix it
3. If they say yes: fix the files and re-test (up to 3 attempts)

### Phase 6: Handoff
Tell the user: "Agent ready at output/{name}/. Run it with: python output/{name}/agent.py"

## Permission Tiers
Choose based on what the agent needs:
- **Read-only**: tools=["Read", "Glob", "Grep"], permission_mode="dontAsk"
- **Read-write**: tools=["Read", "Edit", "Write", "Glob", "Grep"], permission_mode="acceptEdits"
- **Full automation**: tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"], permission_mode="acceptEdits"

## Tool Code Requirements
The tools_code string you pass to write_tools must contain:
- All @tool decorated async functions
- Each function has `if TEST_MODE:` returning mock data as the first check
- A `create_sdk_mcp_server(name="agent-tools", version="1.0.0", tools=[...])` call at the bottom assigned to `tools_server`
- Do NOT include imports or TEST_MODE declaration — the template adds those
```

Create `agent_builder/identity/SOUL.md`:
```markdown
# Agent Builder — Soul

You are a skilled, patient agent architect. You take pride in building well-crafted agents.

## Personality
- Methodical: you follow your workflow phases in order
- Collaborative: you ask questions, propose options, and respect the user's choices
- Practical: you favor simple solutions over clever ones
- Honest: if something won't work well, you say so and suggest alternatives

## Communication Style
- Concise but clear — no fluff, no filler
- Use code blocks when showing tool designs or configurations
- Ask one question at a time during discovery
- Summarize what you're about to build before generating

## Boundaries
- You only build agents — don't try to be a general assistant
- If asked to do something outside agent building, redirect politely
- Never generate tools that access the user's system without their explicit request
```

Create `agent_builder/identity/MEMORY.md`:
```markdown
# Agent Builder — Memory

## Built Agents
No agents built yet. This file will be updated as agents are created.
```

- [ ] **Step 3: Create builder.py entry point**

Create `agent_builder/builder.py`:
```python
"""Agent Builder — interactive CLI for creating Claude Agent SDK agents."""

import asyncio
import argparse
from pathlib import Path

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)

from agent_builder.utils import build_claude_md
from agent_builder.tools import builder_tools_server

BUILDER_DIR = Path(__file__).parent.resolve()
IDENTITY_DIR = BUILDER_DIR / "identity"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Builder — create agents through conversation")
    parser.add_argument("--verbose", action="store_true", help="Show debug output")
    args = parser.parse_args()
    verbose = args.verbose

    # Build CLAUDE.md from builder's own identity files
    build_claude_md(
        source_dir=str(IDENTITY_DIR),
        output_dir=str(BUILDER_DIR),
        verbose=verbose,
    )

    options = ClaudeAgentOptions(
        setting_sources=["project"],
        cwd=str(BUILDER_DIR),
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

    print("\n  Agent Builder ready. Describe what agent you'd like to build.")
    print("  Type 'exit' to quit.\n")

    async with ClaudeSDKClient(options=options) as client:
        while True:
            user_input = await asyncio.to_thread(input, "> ")
            if user_input.strip().lower() in ("exit", "quit"):
                break
            if not user_input.strip():
                continue

            await client.query(user_input)
            async for message in client.receive_response():
                if verbose:
                    print(f"[{message.__class__.__name__}] {message}")

                if isinstance(message, AssistantMessage):
                    if message.error:
                        print(f"[Error: {message.error}]")
                        continue
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text)
                        elif isinstance(block, ToolUseBlock):
                            if verbose:
                                print(f"  [Tool: {block.name}] Input: {block.input}")
                            else:
                                print(f"  [Tool: {block.name}]")
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        print(f"[Failed: {message.subtype}]")
                    if verbose:
                        print(f"  [Session: {message.session_id}]")
                        print(f"  [Turns: {message.num_turns}, Duration: {message.duration_ms}ms]")
                        if message.usage:
                            print(f"  [Tokens: in={message.usage.get('input_tokens', '?')} out={message.usage.get('output_tokens', '?')}]")
                    if message.total_cost_usd:
                        print(f"  [Cost: ${message.total_cost_usd:.4f}]")
                elif verbose and isinstance(message, SystemMessage):
                    if message.subtype == "init":
                        print(f"  [Init: {message.data}]")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Commit**

```bash
git add agent_builder/tools/__init__.py agent_builder/identity/ agent_builder/builder.py
git commit -m "feat: add builder entry point, identity files, and MCP server bundle"
```

---

### Task 9: End-to-End Smoke Test

**Files:** None — this is a manual verification.

- [ ] **Step 1: Run all unit tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Start the builder**

Run: `python -m agent_builder.builder --verbose`

Expected: Builder starts, shows `build_claude_md` verbose output, prints "Agent Builder ready."

- [ ] **Step 3: Build the "codebase-navigator" agent**

In the builder conversation, say:
```
I want a read-only agent that navigates and explains codebases. Call it codebase-navigator. It should have one custom tool called summarize_file that takes a file_path and returns a summary. The agent should be a patient teacher that explains things clearly.
```

Expected: Builder walks through discovery, designs tools, generates files, runs tests, reports success.

- [ ] **Step 4: Verify generated files**

Check that `output/codebase-navigator/` contains:
- `agent.py`
- `tools.py` (with `summarize_file` tool and `TEST_MODE` branch)
- `AGENT.md`
- `SOUL.md`
- `MEMORY.md`
- `CLAUDE.md` (auto-generated)
- `.env.example`
- `.gitignore`

- [ ] **Step 5: Run the generated agent**

Run: `python output/codebase-navigator/agent.py --verbose`

Expected: Agent starts, loads identity files, prints ready message.

- [ ] **Step 6: Commit any fixes**

If any issues were found and fixed during the smoke test:
```bash
git add -A
git commit -m "fix: smoke test fixes for agent builder"
```

---

## Self-Review

### Spec Coverage

| Spec Section | Task(s) |
|---|---|
| Directory structure | Task 1-8 (all files created) |
| Identity files (OpenClaw-inspired) | Task 1 (build_claude_md), Task 4 (write_identity), Task 8 (builder identity) |
| CLAUDE.md build artifact | Task 1 (utils.py) |
| Builder agent config | Task 8 (builder.py) |
| scaffold_agent tool | Task 3 |
| write_identity tool | Task 4 |
| write_tools tool | Task 5 |
| test_agent tool | Task 7 |
| registry tool | Task 6 |
| Conversation flow (phases 1-6) | Task 8 (AGENT.md instructions) |
| Permission tiers | Task 2 (template placeholders), Task 8 (AGENT.md) |
| Mock testing / TEST_MODE | Task 5 (write_tools), Task 7 (test_agent) |
| Debug / verbose mode | Task 2 (template), Task 8 (builder.py) |
| Safety hook | Task 2 (template) |
| Security: path traversal | Task 3 (scaffold validation) |
| Security: try/finally TEST_MODE | Task 7 (test_agent) |
| Security: .gitignore in output | Task 3 (scaffold) |
| First test agent (codebase-navigator) | Task 9 (smoke test) |

### Placeholder Scan
- No TBD/TODO/implement-later in any task
- Template placeholders (`{{agent_name}}`, `{{tools_list}}`, etc.) are intentional — filled by scaffold_agent at generation time

### Type Consistency
- `build_claude_md(source_dir: str, output_dir: str, verbose: bool)` — consistent across Task 1, Task 7, Task 8
- `scaffold_agent(args, output_base)` — consistent across Task 3
- `write_identity(args, output_base)` — consistent across Task 4
- `write_tools(args, output_base)` — consistent across Task 5
- `registry(args, registry_file)` — consistent across Task 6
- `test_agent(args, output_base)` — consistent across Task 7
- All tools return `{"content": [{"type": "text", "text": "..."}]}` with optional `"is_error": True`
