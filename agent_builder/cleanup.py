"""Cleanup helpers — remove stale .bak backups, per-run builder logs, screenshots.

Surfaces through the `--sweep` CLI flag on builder.py. The core function
`sweep_artifacts()` is filesystem-only (no SDK, no cost) and takes an explicit
`repo_root` so tests can point it at `tmp_path`.
"""

import re
import shutil
import time
from pathlib import Path
from typing import Any


# .bak-YYYYMMDD-HHMMSS (edit_agent / propose_self_change format)
_BAK_PATTERN = re.compile(r"\.bak-\d{8}-\d{6}$")

# builder-YYYYMMDD-HHMMSS.log (per-run builder logs)
_BUILDER_LOG_PATTERN = re.compile(r"^builder-\d{8}-\d{6}\.log$")


def _is_bak_file(p: Path) -> bool:
    """True if the file name ends with .bak-<timestamp>.

    Backups can appear on any extension (foo.py.bak-..., AGENT.md.bak-...).
    We match the suffix on the name, not the whole path.
    """
    return bool(_BAK_PATTERN.search(p.name))


def _older_than(path: Path, cutoff_seconds: float) -> bool:
    """True if the file's mtime is older than cutoff_seconds ago.

    cutoff_seconds is an absolute epoch time. Files newer than that are kept.
    """
    try:
        return path.stat().st_mtime < cutoff_seconds
    except OSError:
        # If we can't stat it, don't risk deleting it.
        return False


def _find_bak_files(roots: list[Path], cutoff: float) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and _is_bak_file(p) and _older_than(p, cutoff):
                found.append(p)
    return found


def _find_builder_logs(logs_dir: Path, cutoff: float) -> list[Path]:
    if not logs_dir.exists():
        return []
    return [
        p for p in logs_dir.iterdir()
        if p.is_file()
        and _BUILDER_LOG_PATTERN.match(p.name)
        and _older_than(p, cutoff)
    ]


def _size_bytes(paths: list[Path]) -> int:
    total = 0
    for p in paths:
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


def _dir_size_bytes(d: Path) -> int:
    total = 0
    for p in d.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def sweep_artifacts(
    repo_root: Path,
    older_than_days: int = 7,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Scan + optionally delete stale build artifacts.

    Three kinds of artifacts are swept:
      1. `.bak-<timestamp>` files anywhere under `agent_builder/` or `output/`.
      2. `agent_builder/logs/builder-<timestamp>.log` per-run builder logs.
      3. `screenshots/` directory at the repo root (deleted wholesale when
         older than the cutoff — any file inside newer than cutoff keeps the
         whole dir).

    Returns a summary dict:
        {
          "bak_files": [Path, ...],        # files that were / would be deleted
          "builder_logs": [Path, ...],     # files that were / would be deleted
          "screenshots": Path | None,      # the dir (or None if nothing to do)
          "bytes": int,                    # total bytes of everything above
        }

    `dry_run=True` returns the summary without deleting anything. `dry_run=False`
    deletes matched files / dirs before returning the same summary.
    """
    cutoff = time.time() - (older_than_days * 86400)

    # .bak files live under agent_builder/ and output/.
    bak_roots = [repo_root / "agent_builder", repo_root / "output"]
    bak_files = _find_bak_files(bak_roots, cutoff)

    # Per-run builder logs
    logs_dir = repo_root / "agent_builder" / "logs"
    builder_logs = _find_builder_logs(logs_dir, cutoff)

    # Screenshots dir — only delete if every file inside is older than cutoff.
    # That preserves a recently-taken screenshot even if the dir itself is old.
    screenshots_dir = repo_root / "screenshots"
    screenshots_target: Path | None = None
    screenshots_bytes = 0
    if screenshots_dir.exists() and screenshots_dir.is_dir():
        all_old = True
        for p in screenshots_dir.rglob("*"):
            if p.is_file() and not _older_than(p, cutoff):
                all_old = False
                break
        if all_old:
            screenshots_target = screenshots_dir
            screenshots_bytes = _dir_size_bytes(screenshots_dir)

    total_bytes = (
        _size_bytes(bak_files)
        + _size_bytes(builder_logs)
        + screenshots_bytes
    )

    if not dry_run:
        for p in bak_files:
            try:
                p.unlink()
            except OSError:
                pass
        for p in builder_logs:
            try:
                p.unlink()
            except OSError:
                pass
        if screenshots_target is not None:
            shutil.rmtree(screenshots_target, ignore_errors=True)

    return {
        "bak_files": bak_files,
        "builder_logs": builder_logs,
        "screenshots": screenshots_target,
        "bytes": total_bytes,
    }


def delete_swept(summary: dict[str, Any]) -> None:
    """Delete everything in a summary produced by `sweep_artifacts(dry_run=True)`.

    Splitting delete out of the scan lets the CLI preview + confirm + delete
    with a single filesystem walk instead of walking twice (once for the
    dry-run summary, once more for the real sweep).
    """
    for p in summary.get("bak_files", []):
        try:
            p.unlink()
        except OSError:
            pass
    for p in summary.get("builder_logs", []):
        try:
            p.unlink()
        except OSError:
            pass
    screenshots_target = summary.get("screenshots")
    if screenshots_target is not None:
        shutil.rmtree(screenshots_target, ignore_errors=True)


def format_summary(summary: dict[str, Any]) -> str:
    """Render the summary dict as a human-readable block for the CLI."""
    lines = ["Sweep targets:"]
    bak = summary["bak_files"]
    logs = summary["builder_logs"]
    shots = summary["screenshots"]

    if bak:
        lines.append(f"  .bak files ({len(bak)}):")
        for p in bak:
            lines.append(f"    - {p}")
    else:
        lines.append("  .bak files: none")

    if logs:
        lines.append(f"  builder logs ({len(logs)}):")
        for p in logs:
            lines.append(f"    - {p}")
    else:
        lines.append("  builder logs: none")

    if shots is not None:
        lines.append(f"  screenshots dir: {shots}")
    else:
        lines.append("  screenshots dir: nothing to sweep")

    lines.append(f"Total: {summary['bytes']} bytes")
    return "\n".join(lines)
