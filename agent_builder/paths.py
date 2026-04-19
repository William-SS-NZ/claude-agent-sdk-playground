"""Shared path-containment validator for builder tools.

Four tools previously carried near-identical path-validation code
(``scaffold._validate_agent_name``, ``remove_agent`` inline, and
``rollback``/``self_heal`` ``_validate_target`` variants). This module is the
single source of truth for "does this relative or absolute path resolve under
one of these allowed base directories?". Callers that need extra semantics on
top (slug rules, whitelist/deny-list, backup-name shape checks) stack those
separately.

The validator is deliberately narrow: it does NOT check that the path exists,
does NOT distinguish file from directory, and does NOT perform I/O beyond
``Path.resolve``. Callers decide the rest.
"""

from pathlib import Path
from typing import Iterable


def validate_relative_to_base(
    path: str,
    allowed_bases: Iterable[Path],
    *,
    allow_drive_letter: bool = False,
) -> tuple[Path | None, str | None]:
    """Resolve ``path`` and confirm it lands under one of ``allowed_bases``.

    Returns ``(resolved, None)`` on success, ``(None, error_message)`` on
    failure. The resolved path is always returned via ``Path.resolve()`` so
    callers get a canonical absolute form regardless of whether the input was
    relative or absolute.

    Rejects:
        * Null bytes in the path (classic path-smuggling guard).
        * Anything that resolves outside every supplied base.
        * ``OSError``/``ValueError`` raised by ``Path.resolve`` (reported as
          the error message).

    Does NOT check existence. Does NOT enforce any shape rules on ``path``
    (that's on the caller — e.g. slug regex, relative-only constraint). When
    ``allow_drive_letter`` is false (default) this helper neither rejects nor
    specially interprets drive-letter prefixes; callers that need that guard
    should apply it before calling. The parameter is reserved for future
    platforms where we may want to normalise drive-letter handling centrally.
    """
    if "\x00" in path:
        return None, f"path '{path}' contains null byte"

    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError) as exc:
        return None, f"path '{path}' cannot be resolved: {exc}"

    bases = list(allowed_bases)
    for base in bases:
        base_resolved = Path(base).resolve()
        try:
            resolved.relative_to(base_resolved)
            return resolved, None
        except ValueError:
            continue

    bases_str = ", ".join(str(Path(b).resolve()) for b in bases)
    return None, f"path '{path}' is outside allowed bases [{bases_str}]"
