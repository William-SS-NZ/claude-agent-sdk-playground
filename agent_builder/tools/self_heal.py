"""propose_self_change tool — let the builder edit its own identity, tools, template, or utils after an explicit user confirmation.

This is intentionally conservative:

- Only paths under agent_builder/ are accepted.
- Never touches output/, agent_builder/registry/, tests/, or anything
  outside agent_builder/.
- A synchronous input() prompt pauses the agent; proceed only on a typed
  'y' / 'yes'. No apply without that.
- Both approved and declined proposals are appended to
  agent_builder/self-heal.log so the user has an audit trail.
- The current in-process modules are NOT reloaded. Changes take effect
  on the next session.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder.paths import validate_relative_to_base

BUILDER_DIR = Path(__file__).parent.parent.resolve()
ALLOWED_SUBDIRS = ("identity", "tools", "templates")
ALLOWED_TOP_FILES = ("utils.py", "builder.py")
# Explicit deny list to keep safety-critical surfaces out of reach.
# self_heal.py forbids editing itself so the confirmation gate can't be
# removed via self-heal. registry/agents.json is user data, not code.
DENY_FILES = {
    "registry/agents.json",
    "tools/self_heal.py",
}

AUDIT_LOG_PATH = BUILDER_DIR / "self-heal.log"

# Module-level logger reference with NO FileHandler attached at import time.
# The first call to _get_audit_logger() lazily installs the handler. This
# keeps test runs from opening / polluting the real self-heal.log just by
# importing this module.
_audit_logger = logging.getLogger("agent_builder.self_heal")


def _get_audit_logger() -> logging.Logger:
    """Lazy-init the audit logger. Opens the file handle on first use."""
    if any(hasattr(h, "baseFilename") for h in _audit_logger.handlers):
        return _audit_logger
    handler = logging.FileHandler(AUDIT_LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _audit_logger.addHandler(handler)
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False
    return _audit_logger


def _validate_target(target_path: str) -> tuple[Path | None, str | None]:
    """Return (resolved_path, None) if allowed, else (None, error_message).

    Layered safety check:
      1. Pre-resolution shape check — reject absolute paths and drive-letter
         prefixes (relative-to-``agent_builder/`` contract).
      2. Shared containment — ``validate_relative_to_base`` confirms the
         resolved path lands inside ``BUILDER_DIR``.
      3. Self-heal-specific deny-list (``registry/agents.json``, this file).
      4. Self-heal-specific whitelist (``identity/``, ``tools/``,
         ``templates/``, plus ``utils.py``/``builder.py`` at the top level).
    """
    # Reject leading slashes/backslashes and drive-letter prefixes explicitly
    # because Path("/tmp/x").is_absolute() is False on Windows (no drive letter).
    if target_path.startswith(("/", "\\")) or (len(target_path) > 1 and target_path[1] == ":"):
        return None, "target_path must be a relative path under agent_builder/ (no absolute or drive-letter paths)."

    rel = Path(target_path)
    if rel.is_absolute():
        return None, "target_path must be relative to agent_builder/ (no absolute paths)."

    resolved, err = validate_relative_to_base(
        str(BUILDER_DIR / rel),
        [BUILDER_DIR],
    )
    if err is not None or resolved is None:
        return None, f"target_path escapes agent_builder/: {BUILDER_DIR / rel}"

    rel_inside = resolved.relative_to(BUILDER_DIR)
    rel_posix = rel_inside.as_posix()

    if rel_posix in DENY_FILES:
        return None, f"target_path is on the deny list: {rel_posix}"

    first = rel_inside.parts[0] if rel_inside.parts else ""

    if first in ALLOWED_SUBDIRS:
        return resolved, None
    if len(rel_inside.parts) == 1 and rel_inside.name in ALLOWED_TOP_FILES:
        return resolved, None

    return None, (
        f"target_path '{rel_posix}' not in whitelist. "
        f"Allowed: agent_builder/{{{', '.join(ALLOWED_SUBDIRS)}}}/* "
        f"or agent_builder/{{{', '.join(ALLOWED_TOP_FILES)}}}."
    )


def _render_proposal(summary: str, why: str, target: Path, before: str, after: str) -> str:
    rel = target.relative_to(BUILDER_DIR).as_posix()
    lines = [
        "",
        "=" * 72,
        "  SELF-HEAL PROPOSAL",
        "=" * 72,
        f"  Target : agent_builder/{rel}",
        f"  Summary: {summary}",
        "",
        "  Why:",
    ]
    for line in why.splitlines() or [""]:
        lines.append(f"    {line}")
    lines.extend(["", "  Before:"])
    for line in (before or "(empty)").splitlines():
        lines.append(f"    - {line}")
    lines.append("  After:")
    for line in (after or "(empty)").splitlines():
        lines.append(f"    + {line}")
    lines.extend([
        "=" * 72,
        "  Type 'y' or 'yes' to apply. Anything else cancels.",
        "  Change takes effect on the next builder session.",
        "=" * 72,
        "",
    ])
    return "\n".join(lines)


async def _prompt_confirm() -> bool:
    answer = await asyncio.to_thread(input, "  Apply this change? [y/N]: ")
    return answer.strip().lower() in ("y", "yes")


def _make_backup_path(target: Path) -> Path | None:
    """Return a `.bak-<stamp>` sibling path or None on sub-second collision.

    Matches the rollback tool's collision behaviour (abort, don't clobber)
    so an `edit_agent` / `propose_self_change` loop can't silently lose the
    original by overwriting a just-written backup.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = target.with_suffix(target.suffix + f".bak-{stamp}")
    if candidate.exists():
        return None
    return candidate


async def propose_self_change(args: dict[str, Any]) -> dict[str, Any]:
    target_path: str = args["target_path"]
    summary: str = args["summary"]
    why: str = args["why"]
    before_snippet: str = args.get("before_snippet", "")
    after_snippet: str = args.get("after_snippet", "")
    old_string: str | None = args.get("old_string")
    new_string: str | None = args.get("new_string")
    full_content: str | None = args.get("full_content")

    resolved, err = _validate_target(target_path)
    if err or resolved is None:
        _get_audit_logger().warning("REJECTED_TARGET target=%s reason=%s", target_path, err)
        return {
            "content": [{"type": "text", "text": err or "invalid target"}],
            "is_error": True,
        }

    if full_content is None and (old_string is None or new_string is None):
        return {
            "content": [{"type": "text", "text": "Must supply either full_content, or both old_string and new_string."}],
            "is_error": True,
        }
    if full_content is not None and (old_string is not None or new_string is not None):
        return {
            "content": [{"type": "text", "text": "Pass exactly one of: full_content, or (old_string + new_string)."}],
            "is_error": True,
        }

    # Print proposal, pause, ask.
    print(_render_proposal(summary, why, resolved, before_snippet, after_snippet))
    approved = await _prompt_confirm()

    rel = resolved.relative_to(BUILDER_DIR).as_posix()
    if not approved:
        _get_audit_logger().info(
            "DECLINED target=%s summary=%s",
            f"agent_builder/{rel}", summary,
        )
        return {
            "content": [{"type": "text", "text": f"User declined self-heal change to agent_builder/{rel}."}]
        }

    # Apply
    if full_content is not None:
        if resolved.exists():
            backup = _make_backup_path(resolved)
            if backup is None:
                _get_audit_logger().warning(
                    "APPLY_FAILED target=%s reason=backup_collision",
                    f"agent_builder/{rel}",
                )
                return {
                    "content": [{"type": "text", "text": (
                        f"backup path for {rel} already exists — refusing to clobber. "
                        "Wait a second and retry."
                    )}],
                    "is_error": True,
                }
            backup.write_text(resolved.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            backup = None
        resolved.write_text(full_content, encoding="utf-8")
        change_summary = f"wrote {len(full_content)} chars" + (f" (backup: {backup.name})" if backup else " (new file)")
    else:
        current = resolved.read_text(encoding="utf-8")
        if old_string not in current:
            _get_audit_logger().warning(
                "APPLY_FAILED target=%s reason=old_string_not_found",
                f"agent_builder/{rel}",
            )
            return {
                "content": [{"type": "text", "text": f"old_string not found in {rel} — change not applied. Re-read the file and resubmit."}],
                "is_error": True,
            }
        if current.count(old_string) > 1:
            _get_audit_logger().warning(
                "APPLY_FAILED target=%s reason=old_string_ambiguous",
                f"agent_builder/{rel}",
            )
            return {
                "content": [{"type": "text", "text": f"old_string matches {current.count(old_string)} places in {rel} — include more surrounding context to make it unique."}],
                "is_error": True,
            }
        backup = _make_backup_path(resolved)
        if backup is None:
            _get_audit_logger().warning(
                "APPLY_FAILED target=%s reason=backup_collision",
                f"agent_builder/{rel}",
            )
            return {
                "content": [{"type": "text", "text": (
                    f"backup path for {rel} already exists — refusing to clobber. "
                    "Wait a second and retry."
                )}],
                "is_error": True,
            }
        backup.write_text(current, encoding="utf-8")
        resolved.write_text(current.replace(old_string, new_string, 1), encoding="utf-8")
        change_summary = f"replaced {len(old_string)} chars with {len(new_string)} (backup: {backup.name})"

    _get_audit_logger().info(
        "APPLIED target=%s summary=%s change=%s",
        f"agent_builder/{rel}", summary, change_summary,
    )
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Applied self-heal to agent_builder/{rel}: {change_summary}.\n"
                    f"Audit log: {AUDIT_LOG_PATH.name}. Change takes effect on next session."
                ),
            }
        ]
    }


propose_self_change_tool = tool(
    "propose_self_change",
    "Propose a change to the builder's own identity, tools, template, or utils "
    "(never output/, registry, or anything outside agent_builder/). Shows the "
    "human-readable summary + before/after snippets, blocks on a hard stdin "
    "confirmation, then either applies the edit (with a .bak-<timestamp> "
    "backup) or records a decline. Both outcomes are appended to "
    "agent_builder/self-heal.log. Changes take effect on the next builder "
    "session — the current process does not reload.",
    {
        "type": "object",
        "properties": {
            "target_path": {
                "type": "string",
                "description": "Path relative to agent_builder/, e.g. 'identity/AGENT.md' or 'tools/scaffold.py'.",
            },
            "summary": {
                "type": "string",
                "description": "One-sentence human summary of what will change.",
            },
            "why": {
                "type": "string",
                "description": "Observed problem or improvement reason. Cite the specific failure that prompted this.",
            },
            "before_snippet": {
                "type": "string",
                "description": "A few lines showing the current state (no full-file dumps).",
            },
            "after_snippet": {
                "type": "string",
                "description": "A few lines showing the proposed state (no full-file dumps).",
            },
            "old_string": {
                "type": "string",
                "description": "Exact existing text to replace. Required unless full_content is supplied.",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text. Required unless full_content is supplied.",
            },
            "full_content": {
                "type": "string",
                "description": "Alternative to old_string/new_string — full file contents to write. Use only for small files.",
            },
        },
        "required": ["target_path", "summary", "why"],
    },
)(propose_self_change)
