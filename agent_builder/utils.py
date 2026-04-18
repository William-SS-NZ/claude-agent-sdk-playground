"""Shared utilities for the Agent Builder."""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any


class Spinner:
    """Async stderr spinner with live token + cost readout.

    Usage:
        spinner = Spinner("thinking")
        spinner.start()
        spinner.add_tokens(input_tokens=123, output_tokens=45)
        spinner.set_cost(0.12)  # usually from ResultMessage.total_cost_usd
        with spinner.paused():
            print("tool output")
        await spinner.stop()
    """

    FRAMES = ("|", "/", "-", "\\")

    # Per-million-token pricing for live cost approximation until the SDK
    # returns an authoritative total_cost_usd. Defaults to Claude Opus 4.x.
    INPUT_PRICE_PER_MT = 15.0
    OUTPUT_PRICE_PER_MT = 75.0

    def __init__(self, label: str = "working", stream=sys.stderr) -> None:
        self.label = label
        self.stream = stream
        self._task: asyncio.Task | None = None
        self._paused = False
        self._started_at: float | None = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd: float | None = None  # None means "use estimate"

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def set_cost(self, usd: float) -> None:
        """Override the live estimate with an authoritative value."""
        self.cost_usd = usd

    def _estimated_cost(self) -> float:
        if self.cost_usd is not None:
            return self.cost_usd
        return (
            self.input_tokens * self.INPUT_PRICE_PER_MT / 1_000_000
            + self.output_tokens * self.OUTPUT_PRICE_PER_MT / 1_000_000
        )

    def _render_line(self) -> str:
        elapsed = time.monotonic() - (self._started_at or time.monotonic())
        frame = self.FRAMES[int(elapsed * 10) % len(self.FRAMES)]
        parts = [f"\r  {frame} {self.label} ({elapsed:5.1f}s)"]
        if self.input_tokens or self.output_tokens:
            total_tok = self.input_tokens + self.output_tokens
            parts.append(f" | {total_tok:>6,} tok")
            cost = self._estimated_cost()
            cost_tag = "$" if self.cost_usd is not None else "~$"
            parts.append(f" | {cost_tag}{cost:.4f}")
            if elapsed > 1.0:
                per_min = cost / (elapsed / 60)
                parts.append(f" | {cost_tag}{per_min:.2f}/min")
        return "".join(parts)

    async def _spin(self) -> None:
        try:
            while True:
                if not self._paused:
                    self.stream.write(self._render_line())
                    self.stream.flush()
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            self._clear()
            raise

    def _clear(self) -> None:
        self.stream.write("\r" + " " * 120 + "\r")
        self.stream.flush()

    def start(self) -> None:
        if self._task is not None:
            return
        self._started_at = time.monotonic()
        self._task = asyncio.create_task(self._spin())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._clear()

    class _Pause:
        def __init__(self, spinner: "Spinner") -> None:
            self.spinner = spinner

        def __enter__(self):
            self.spinner._paused = True
            self.spinner._clear()
            return self

        def __exit__(self, *exc) -> None:
            self.spinner._paused = False

    def paused(self) -> "_Pause":
        return Spinner._Pause(self)


CLAUDE_MD_HEADER = "<!-- AUTO-GENERATED: Do not edit. Modify AGENT.md, SOUL.md, MEMORY.md, or USER.md instead. -->\n\n"


def _truncate(s: Any, limit: int = 80) -> str:
    """Collapse whitespace + truncate so tool previews stay on one line.

    `s` is `Any` because callers pass tool-input scalars (str / int / float / bool)
    straight in; the body stringifies before doing anything else.
    """
    text = " ".join(str(s).split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


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
