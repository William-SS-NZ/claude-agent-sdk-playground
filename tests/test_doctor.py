"""Tests for agent_builder.doctor.run_health_check."""

import json
from pathlib import Path

from agent_builder.doctor import (
    EXPECTED_TEMPLATE_PLACEHOLDERS,
    run_health_check,
)
from agent_builder.tools.registry import REQUIRED_AGENT_FILES


def _seed_builder(root: Path, template_placeholders=EXPECTED_TEMPLATE_PLACEHOLDERS) -> Path:
    """Create a well-formed builder skeleton at `root`. Returns registry path."""
    builder = root / "agent_builder"
    (builder / "identity").mkdir(parents=True)
    (builder / "identity" / "AGENT.md").write_text("# Agent", encoding="utf-8")
    (builder / "identity" / "SOUL.md").write_text("# Soul", encoding="utf-8")
    (builder / "identity" / "MEMORY.md").write_text("# Memory", encoding="utf-8")

    (builder / "templates").mkdir()
    template_body = "# template\n" + "\n".join(template_placeholders) + "\n"
    (builder / "templates" / "agent_main.py.tmpl").write_text(template_body, encoding="utf-8")

    (builder / "registry").mkdir()
    registry_path = builder / "registry" / "agents.json"
    registry_path.write_text("[]", encoding="utf-8")

    (root / "output").mkdir()
    return registry_path


def _make_agent_dir(output: Path, name: str, with_placeholder: bool = False) -> None:
    """Create a fully-fledged output/<name>/ with all required files."""
    d = output / name
    d.mkdir()
    for f in REQUIRED_AGENT_FILES:
        if f == "agent.py" and with_placeholder:
            (d / f).write_text("print('{{agent_name}}')\n", encoding="utf-8")
        else:
            (d / f).write_text(f"# {f}\n", encoding="utf-8")


def test_doctor_all_ok_returns_exit_zero(tmp_path: Path):
    registry = _seed_builder(tmp_path)
    _make_agent_dir(tmp_path / "output", "alpha")
    registry.write_text(json.dumps([
        {"name": "alpha", "description": "x", "tools": [], "created": "2026-01-01", "path": "output/alpha/", "status": "active"},
    ]), encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    assert exit_code == 0
    assert not any(c["status"] == "FAIL" for c in checks)


def test_doctor_warns_on_orphan_output_dir(tmp_path: Path):
    registry = _seed_builder(tmp_path)
    # An agent dir exists on disk but is NOT in the registry.
    _make_agent_dir(tmp_path / "output", "orphan")
    registry.write_text("[]", encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    warn_names = [c for c in checks if c["status"] == "WARN"]
    assert any("orphan" in c["name"] for c in warn_names)
    # WARN doesn't fail exit.
    assert exit_code == 0


def test_doctor_fails_when_registered_agent_dir_missing(tmp_path: Path):
    registry = _seed_builder(tmp_path)
    # Registry lists "ghost" but no output/ghost/ on disk.
    registry.write_text(json.dumps([
        {"name": "ghost", "description": "x", "tools": [], "created": "2026-01-01", "path": "output/ghost/", "status": "active"},
    ]), encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    fails = [c for c in checks if c["status"] == "FAIL"]
    assert any("ghost" in c["name"] for c in fails)
    assert exit_code == 1


def test_doctor_fails_on_template_placeholder_drift(tmp_path: Path):
    # Seed a builder where the template is missing one required placeholder.
    drifted = [p for p in EXPECTED_TEMPLATE_PLACEHOLDERS if p != "{{max_turns}}"]
    registry = _seed_builder(tmp_path, template_placeholders=drifted)
    _make_agent_dir(tmp_path / "output", "alpha")
    registry.write_text(json.dumps([
        {"name": "alpha", "description": "x", "tools": [], "created": "2026-01-01", "path": "output/alpha/", "status": "active"},
    ]), encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    fails = [c for c in checks if c["status"] == "FAIL"]
    assert any("template" in c["name"].lower() for c in fails)
    assert exit_code == 1


def test_doctor_fails_on_unfilled_placeholder_in_agent_py(tmp_path: Path):
    registry = _seed_builder(tmp_path)
    _make_agent_dir(tmp_path / "output", "broken", with_placeholder=True)
    registry.write_text(json.dumps([
        {"name": "broken", "description": "x", "tools": [], "created": "2026-01-01", "path": "output/broken/", "status": "active"},
    ]), encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    fails = [c for c in checks if c["status"] == "FAIL"]
    assert any("placeholders in broken/agent.py" in c["name"] for c in fails)
    assert exit_code == 1


def test_doctor_fails_when_registry_not_a_list(tmp_path: Path):
    registry = _seed_builder(tmp_path)
    registry.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    fails = [c for c in checks if c["status"] == "FAIL"]
    assert any("registry" in c["name"].lower() for c in fails)
    assert exit_code == 1


def test_doctor_fails_when_builder_identity_missing(tmp_path: Path):
    registry = _seed_builder(tmp_path)
    # Remove one identity file.
    (tmp_path / "agent_builder" / "identity" / "SOUL.md").unlink()

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    fails = [c for c in checks if c["status"] == "FAIL"]
    assert any("SOUL.md" in c["name"] for c in fails)
    assert exit_code == 1


def test_doctor_placeholders_match_scaffold_required():
    """Doctor's placeholder list must be the same object scaffold fills in.

    The whole point of the doctor template check is to catch drift. If this
    ever split into two independent lists again, a placeholder scaffold
    expects could go missing in the template without doctor flagging it.
    """
    from agent_builder.tools.scaffold import REQUIRED_PLACEHOLDERS

    assert EXPECTED_TEMPLATE_PLACEHOLDERS is REQUIRED_PLACEHOLDERS


def test_doctor_fails_on_missing_builder_version_placeholder(tmp_path: Path):
    """Regression: pre-fix, doctor missed {{builder_version}} drift entirely."""
    placeholders_missing_version = tuple(
        p for p in EXPECTED_TEMPLATE_PLACEHOLDERS if p != "{{builder_version}}"
    )
    registry = _seed_builder(tmp_path, template_placeholders=placeholders_missing_version)

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    fails = [c for c in checks if c["status"] == "FAIL"]
    assert any("{{builder_version}}" in c["detail"] for c in fails)
    assert exit_code == 1
