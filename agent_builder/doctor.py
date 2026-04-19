"""Doctor — read-only health check for the agent builder.

Surfaces through the `--doctor` CLI flag. All checks are filesystem-only
(no SDK, no API call). Each check returns one of:
    status ∈ {"OK", "WARN", "FAIL"}
    name  : short label
    detail: one-line description shown to the user

Exit code rules:
    * Any FAIL → exit 1
    * WARN only → exit 0 (warnings don't fail the check)
    * No issues → exit 0
"""

import json
import re
from pathlib import Path
from typing import Any

from agent_builder.tools.registry import DEFAULT_REGISTRY, REQUIRED_AGENT_FILES
from agent_builder.tools.scaffold import REQUIRED_PLACEHOLDERS as EXPECTED_TEMPLATE_PLACEHOLDERS

BUILDER_IDENTITY_FILES = ("AGENT.md", "SOUL.md", "MEMORY.md")

EXPECTED_AGENT_MD_SLOTS = (
    "{{slot:purpose}}",
    "{{slot:workflow}}",
    "{{slot:constraints}}",
    "{{slot:tools_reference}}",
    "{{slot:examples}}",
    "{{slot:first_run_setup}}",
    "{{slot:builder_agent_additions}}",
    "{{slot:user_additions}}",
)

_UNFILLED_PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}")


def _check(status: str, name: str, detail: str) -> dict[str, str]:
    return {"status": status, "name": name, "detail": detail}


def _check_registry_parses(registry_path: Path) -> tuple[dict[str, str], list[dict[str, Any]] | None]:
    """Check registry JSON loads and is a list. Returns (check, parsed|None)."""
    if not registry_path.exists():
        return (
            _check("WARN", "registry exists", f"{registry_path} not found — no agents registered"),
            [],
        )
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return (
            _check("FAIL", "registry parses", f"{registry_path} is not valid JSON: {e}"),
            None,
        )
    if not isinstance(data, list):
        return (
            _check("FAIL", "registry shape", f"{registry_path} top-level must be a list, got {type(data).__name__}"),
            None,
        )
    return (
        _check("OK", "registry parses", f"{len(data)} agent(s) registered"),
        data,
    )


def _check_registered_agents_present(
    registry_entries: list[dict[str, Any]],
    output_dir: Path,
) -> list[dict[str, str]]:
    """For each registry entry, verify output/<name>/ + all REQUIRED_AGENT_FILES exist."""
    checks: list[dict[str, str]] = []
    for entry in registry_entries:
        name = entry.get("name", "")
        if not name:
            checks.append(_check("FAIL", "registry entry", "entry missing 'name' field"))
            continue
        agent_dir = output_dir / name
        if not agent_dir.exists():
            checks.append(_check(
                "FAIL",
                f"agent dir: {name}",
                f"registry says '{name}' exists but {agent_dir} is missing",
            ))
            continue
        missing = [f for f in REQUIRED_AGENT_FILES if not (agent_dir / f).exists()]
        if missing:
            checks.append(_check(
                "FAIL",
                f"agent files: {name}",
                f"missing required files in {agent_dir}: {missing}",
            ))
        else:
            checks.append(_check(
                "OK",
                f"agent files: {name}",
                f"all {len(REQUIRED_AGENT_FILES)} required files present",
            ))
    return checks


def _check_orphan_output_dirs(
    registry_entries: list[dict[str, Any]],
    output_dir: Path,
) -> list[dict[str, str]]:
    """Warn about output/<name>/ dirs that aren't in the registry."""
    checks: list[dict[str, str]] = []
    if not output_dir.exists():
        return checks
    registered = {e.get("name") for e in registry_entries if e.get("name")}
    for d in output_dir.iterdir():
        if not d.is_dir():
            continue
        if d.name in registered:
            continue
        checks.append(_check(
            "WARN",
            f"orphan output dir: {d.name}",
            f"{d} exists on disk but has no registry entry",
        ))
    return checks


def _check_builder_identity(builder_dir: Path) -> list[dict[str, str]]:
    """Verify the builder's own identity files exist."""
    checks: list[dict[str, str]] = []
    identity_dir = builder_dir / "identity"
    for fname in BUILDER_IDENTITY_FILES:
        p = identity_dir / fname
        if p.exists():
            checks.append(_check("OK", f"builder identity: {fname}", str(p)))
        else:
            checks.append(_check("FAIL", f"builder identity: {fname}", f"missing: {p}"))
    return checks


def _check_template_placeholders(builder_dir: Path) -> dict[str, str]:
    """Verify the scaffold template still contains every expected placeholder."""
    template_path = builder_dir / "templates" / "agent_main.py.tmpl"
    if not template_path.exists():
        return _check("FAIL", "scaffold template", f"missing: {template_path}")
    content = template_path.read_text(encoding="utf-8")
    missing = [ph for ph in EXPECTED_TEMPLATE_PLACEHOLDERS if ph not in content]
    if missing:
        return _check(
            "FAIL",
            "scaffold template placeholders",
            f"{template_path} is missing: {missing}",
        )
    return _check(
        "OK",
        "scaffold template placeholders",
        f"all {len(EXPECTED_TEMPLATE_PLACEHOLDERS)} placeholders present",
    )


def _check_agent_md_template(builder_dir: Path) -> list[dict[str, str]]:
    path = builder_dir / "templates" / "agent_md.tmpl"
    if not path.exists():
        return [_check("FAIL", "agent_md template", f"missing: {path}")]
    content = path.read_text(encoding="utf-8")
    missing = [s for s in EXPECTED_AGENT_MD_SLOTS if s not in content]
    if missing:
        return [_check("FAIL", "agent_md slots", f"missing slots: {missing}")]
    return [_check("OK", "agent_md slots", f"all {len(EXPECTED_AGENT_MD_SLOTS)} present")]


def _check_generated_agents_no_placeholders(output_dir: Path) -> list[dict[str, str]]:
    """Every output/<name>/agent.py must be free of unfilled {{...}} placeholders."""
    checks: list[dict[str, str]] = []
    if not output_dir.exists():
        return checks
    for d in output_dir.iterdir():
        if not d.is_dir():
            continue
        agent_py = d / "agent.py"
        if not agent_py.exists():
            continue
        try:
            content = agent_py.read_text(encoding="utf-8")
        except OSError as e:
            checks.append(_check(
                "WARN",
                f"scan agent.py: {d.name}",
                f"could not read {agent_py}: {e}",
            ))
            continue
        leftovers = sorted(set(_UNFILLED_PLACEHOLDER.findall(content)))
        if leftovers:
            checks.append(_check(
                "FAIL",
                f"placeholders in {d.name}/agent.py",
                f"unfilled: {leftovers}",
            ))
        else:
            checks.append(_check(
                "OK",
                f"placeholders in {d.name}/agent.py",
                "no unfilled placeholders",
            ))
    return checks


def run_health_check(
    repo_root: Path,
    registry_file: str = DEFAULT_REGISTRY,
) -> tuple[list[dict[str, str]], int]:
    """Run every doctor check and return (checks, exit_code).

    Exit code is 1 if any check is FAIL, else 0.
    """
    checks: list[dict[str, str]] = []
    builder_dir = repo_root / "agent_builder"
    output_dir = repo_root / "output"
    registry_path = Path(registry_file)

    # 1 + 2. Registry parses + per-entry agent files complete.
    reg_check, reg_entries = _check_registry_parses(registry_path)
    checks.append(reg_check)
    if reg_entries is not None:
        checks.extend(_check_registered_agents_present(reg_entries, output_dir))
        # 3. Orphan output dirs (WARN).
        checks.extend(_check_orphan_output_dirs(reg_entries, output_dir))

    # 4. Builder identity files.
    checks.extend(_check_builder_identity(builder_dir))

    # 5. Scaffold template placeholders intact.
    checks.append(_check_template_placeholders(builder_dir))

    # 6. AGENT.md slot template intact.
    checks.extend(_check_agent_md_template(builder_dir))

    # 7. Generated agents have no unfilled placeholders.
    checks.extend(_check_generated_agents_no_placeholders(output_dir))

    exit_code = 1 if any(c["status"] == "FAIL" for c in checks) else 0
    return checks, exit_code


def format_checks(checks: list[dict[str, str]]) -> str:
    lines = []
    for c in checks:
        lines.append(f"[{c['status']:<4}] {c['name']}: {c['detail']}")
    return "\n".join(lines)
