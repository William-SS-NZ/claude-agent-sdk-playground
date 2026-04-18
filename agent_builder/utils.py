"""Shared utilities for the Agent Builder."""

from pathlib import Path
from typing import Any

CLAUDE_MD_HEADER = "<!-- AUTO-GENERATED: Do not edit. Modify AGENT.md, SOUL.md, MEMORY.md, or USER.md instead. -->\n\n"


def _truncate(s: str, limit: int = 80) -> str:
    """Collapse whitespace + truncate so tool previews stay on one line."""
    s = " ".join(str(s).split())
    return s if len(s) <= limit else s[: limit - 1] + "..."


def format_tool_call(name: str, tool_input: dict[str, Any]) -> str:
    """Render a short one-line summary of a tool call for the user.

    Picks the most informative field per tool. Falls back to listing the
    first key=value pair for unknown tools.
    """
    short_name = name.split("__")[-1] if name.startswith("mcp__") else name

    previews: dict[str, tuple[str, ...]] = {
        "Bash": ("command",),
        "Read": ("file_path",),
        "Edit": ("file_path",),
        "Write": ("file_path",),
        "Glob": ("pattern",),
        "Grep": ("pattern",),
        "WebFetch": ("url",),
        "WebSearch": ("query",),
    }

    keys = previews.get(short_name)
    if not keys and name.startswith("mcp__"):
        keys = ("action", "agent_name", "url", "prompt")

    if keys:
        for k in keys:
            v = tool_input.get(k)
            if v:
                if k == "test_prompts" and isinstance(v, list):
                    v = f"{len(v)} prompts"
                return f"  [Tool: {short_name}] {k}={_truncate(v)}"

    # Unknown tool — preview first scalar arg
    for k, v in tool_input.items():
        if isinstance(v, (str, int, float, bool)):
            return f"  [Tool: {short_name}] {k}={_truncate(v)}"
    return f"  [Tool: {short_name}]"

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
