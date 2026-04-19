"""rollback tool — list and restore `.bak-<timestamp>` backups produced by
`propose_self_change` and `edit_agent`.

Both of those tools write a `<file>.bak-YYYYMMDD-HHMMSS` next to the file
they overwrite, but until now there was no UX to inspect or undo one.
This tool fills that gap with two actions:

- ``list``: enumerate every backup sitting next to a target file, newest
  first, with timestamp and size.
- ``restore``: copy a specific backup back over the target. Before doing
  so it writes a fresh `.bak-<now>` of the current target, so even the
  restore itself is reversible.

Safety:

- ``target_path`` must be a relative path, and after resolution must land
  under one of the accepted bases: the repo root, ``agent_builder/``, or
  ``output/``. Absolute paths, drive letters, and ``..`` escapes are
  rejected before any filesystem access.
- ``backup_name`` must be a plain basename (no directory separators), must
  live in the same directory as the target, and must match the pattern
  ``<target_basename>.bak-<timestamp>``. This prevents restoring an
  unrelated backup (e.g. ``AGENT.md.bak-...`` over ``tools.py``) and
  prevents traversal via the backup_name argument.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

# Repo root = two levels up from this file (agent_builder/tools/rollback.py).
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
BUILDER_DIR = REPO_ROOT / "agent_builder"
OUTPUT_DIR = REPO_ROOT / "output"

# A backup name is <something>.bak-<8digits>-<6digits>. Keep the stamp
# shape strict so stray files named like `foo.bak-oops` are rejected.
_BAK_STAMP_RE = re.compile(r"^(?P<base>.+)\.bak-(?P<stamp>\d{8}-\d{6})$")


def _validate_target(target_path: str) -> tuple[Path | None, str | None]:
    """Return (resolved_path, None) if allowed, else (None, error_message).

    Accepts any relative path that, after resolution, lands under the repo
    root, ``agent_builder/``, or ``output/``. Rejects absolute paths,
    Windows drive letters, and ``..`` escapes.
    """
    if not target_path:
        return None, "target_path must not be empty."

    # Mirror self_heal._validate_target: Path("/tmp/x").is_absolute() is
    # False on Windows when there's no drive letter, so reject those
    # shapes explicitly.
    if target_path.startswith(("/", "\\")) or (len(target_path) > 1 and target_path[1] == ":"):
        return None, "target_path must be a relative path (no absolute or drive-letter paths)."

    rel = Path(target_path)
    if rel.is_absolute():
        return None, "target_path must be a relative path."

    resolved = (REPO_ROOT / rel).resolve()

    allowed_bases = (REPO_ROOT, BUILDER_DIR, OUTPUT_DIR)
    for base in allowed_bases:
        try:
            resolved.relative_to(base)
            return resolved, None
        except ValueError:
            continue

    return None, (
        f"target_path '{target_path}' escapes allowed roots. "
        f"Must resolve under the repo root, agent_builder/, or output/."
    )


def _validate_backup_name(backup_name: str, target: Path) -> tuple[Path | None, str | None]:
    """Return (resolved_backup_path, None) if it's a legal sibling of target.

    The name must be a plain basename (no path separators), must match
    ``<target.name>.bak-<stamp>``, and must exist next to the target.
    """
    if not backup_name:
        return None, "backup_name must not be empty."

    # Path separators or parent refs in the name are always a red flag.
    if "/" in backup_name or "\\" in backup_name or ".." in backup_name:
        return None, f"backup_name must be a plain basename, got '{backup_name}'."

    # Use Path to pick off the name portion and confirm it's the whole string.
    if Path(backup_name).name != backup_name:
        return None, f"backup_name must be a plain basename, got '{backup_name}'."

    match = _BAK_STAMP_RE.match(backup_name)
    if not match:
        return None, (
            f"backup_name '{backup_name}' does not match <basename>.bak-<YYYYMMDD-HHMMSS>."
        )

    if match.group("base") != target.name:
        return None, (
            f"backup_name '{backup_name}' does not belong to target '{target.name}' "
            f"(expected prefix '{target.name}.bak-')."
        )

    backup_path = (target.parent / backup_name).resolve()

    # Defence in depth: even though we built the path ourselves, re-check
    # that resolution didn't escape the target's directory.
    try:
        backup_path.relative_to(target.parent.resolve())
    except ValueError:
        return None, f"backup_name '{backup_name}' resolves outside the target directory."

    return backup_path, None


def _stamp_from_backup_name(name: str) -> str:
    match = _BAK_STAMP_RE.match(name)
    return match.group("stamp") if match else ""


async def rollback(args: dict[str, Any]) -> dict[str, Any]:
    action = args.get("action")
    target_path = args.get("target_path")

    if action not in ("list", "restore"):
        return {
            "content": [{"type": "text", "text": "action must be 'list' or 'restore'."}],
            "is_error": True,
        }

    if not target_path or not isinstance(target_path, str):
        return {
            "content": [{"type": "text", "text": "target_path is required and must be a string."}],
            "is_error": True,
        }

    resolved_target, err = _validate_target(target_path)
    if err or resolved_target is None:
        return {
            "content": [{"type": "text", "text": err or "invalid target"}],
            "is_error": True,
        }

    if action == "list":
        return _list_backups(resolved_target, target_path)

    # action == "restore"
    backup_name = args.get("backup_name")
    if not backup_name or not isinstance(backup_name, str):
        return {
            "content": [{"type": "text", "text": "backup_name is required for action='restore'."}],
            "is_error": True,
        }
    return _restore_backup(resolved_target, target_path, backup_name)


def _list_backups(resolved_target: Path, display_path: str) -> dict[str, Any]:
    parent = resolved_target.parent
    if not parent.exists():
        return {
            "content": [{"type": "text", "text": f"no backups found for {display_path} (directory does not exist)."}],
        }

    candidates = []
    prefix = resolved_target.name + ".bak-"
    for entry in parent.iterdir():
        if not entry.is_file():
            continue
        if not entry.name.startswith(prefix):
            continue
        match = _BAK_STAMP_RE.match(entry.name)
        if not match or match.group("base") != resolved_target.name:
            continue
        candidates.append(entry)

    if not candidates:
        return {
            "content": [{"type": "text", "text": f"no backups found for {display_path}."}],
        }

    # Newest first by the embedded stamp (lexicographic == chronological
    # because the format is YYYYMMDD-HHMMSS).
    candidates.sort(key=lambda p: _stamp_from_backup_name(p.name), reverse=True)

    lines = [f"Found {len(candidates)} backup(s) for {display_path}:"]
    for p in candidates:
        stamp = _stamp_from_backup_name(p.name)
        try:
            pretty = datetime.strptime(stamp, "%Y%m%d-%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pretty = stamp
        size = p.stat().st_size
        lines.append(f"  - {p.name}  ({pretty}, {size} bytes)")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def _restore_backup(resolved_target: Path, display_path: str, backup_name: str) -> dict[str, Any]:
    backup_path, err = _validate_backup_name(backup_name, resolved_target)
    if err or backup_path is None:
        return {
            "content": [{"type": "text", "text": err or "invalid backup_name"}],
            "is_error": True,
        }

    if not backup_path.exists() or not backup_path.is_file():
        return {
            "content": [{"type": "text", "text": f"backup not found: {backup_name}"}],
            "is_error": True,
        }

    # Write a fresh pre-restore backup of the *current* target so the
    # restore itself is reversible. If the target doesn't exist we simply
    # skip this step.
    pre_restore_name: str | None = None
    if resolved_target.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        pre_restore = resolved_target.with_suffix(resolved_target.suffix + f".bak-{stamp}")
        # Extremely unlikely, but if a second-granularity collision occurs,
        # bail rather than silently clobber.
        if pre_restore.exists():
            return {
                "content": [{"type": "text", "text": (
                    f"pre-restore backup path already exists: {pre_restore.name}. "
                    "Wait a second and try again."
                )}],
                "is_error": True,
            }
        pre_restore.write_bytes(resolved_target.read_bytes())
        pre_restore_name = pre_restore.name

    resolved_target.write_bytes(backup_path.read_bytes())

    parts = [
        f"Restored {display_path} from {backup_name}.",
    ]
    if pre_restore_name:
        parts.append(f"Pre-restore backup written: {pre_restore_name}")
    else:
        parts.append("No pre-restore backup written (target did not exist).")
    return {"content": [{"type": "text", "text": "\n".join(parts)}]}


rollback_tool = tool(
    "rollback",
    "List or restore `.bak-<timestamp>` backups created by propose_self_change "
    "and edit_agent. action='list' enumerates every <basename>.bak-* sitting "
    "next to target_path, newest first. action='restore' copies a chosen "
    "backup over the target after first writing a fresh pre-restore backup "
    "of the current file, so the restore is itself reversible. target_path "
    "must be relative and resolve under the repo root, agent_builder/, or "
    "output/. backup_name must be a plain basename of the form "
    "'<target_basename>.bak-<YYYYMMDD-HHMMSS>' sitting next to target_path.",
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "restore"],
                "description": "'list' to enumerate backups, 'restore' to revert target_path to a chosen backup.",
            },
            "target_path": {
                "type": "string",
                "description": "Path (relative to repo root) of the file whose backups you want to inspect or restore, e.g. 'agent_builder/identity/AGENT.md' or 'output/my-agent/tools.py'.",
            },
            "backup_name": {
                "type": "string",
                "description": "Required for action='restore'. Plain basename of the backup to restore, e.g. 'AGENT.md.bak-20260418-153045'. Must sit next to target_path.",
            },
        },
        "required": ["action", "target_path"],
    },
)(rollback)
