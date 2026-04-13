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
