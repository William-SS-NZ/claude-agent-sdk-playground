"""Tests for agent_builder.doctor.run_health_check."""

import json
from pathlib import Path

from agent_builder.doctor import (
    EXPECTED_AGENT_MD_SLOTS,
    EXPECTED_TEMPLATE_PLACEHOLDERS,
    run_health_check,
)
from agent_builder.tools.registry import REQUIRED_AGENT_FILES
from agent_builder.tools.scaffold import REQUIRED_PLACEHOLDERS_BY_MODE


def _seed_builder(
    root: Path,
    template_placeholders=EXPECTED_TEMPLATE_PLACEHOLDERS,
    poll_template_placeholders=None,
) -> Path:
    """Create a well-formed builder skeleton at `root`. Returns registry path."""
    builder = root / "agent_builder"
    (builder / "identity").mkdir(parents=True)
    (builder / "identity" / "AGENT.md").write_text("# Agent", encoding="utf-8")
    (builder / "identity" / "SOUL.md").write_text("# Soul", encoding="utf-8")
    (builder / "identity" / "MEMORY.md").write_text("# Memory", encoding="utf-8")

    (builder / "templates").mkdir()
    template_body = "# template\n" + "\n".join(template_placeholders) + "\n"
    (builder / "templates" / "agent_main.py.tmpl").write_text(template_body, encoding="utf-8")

    # Seed a valid poll template too so doctor's per-mode check has both to
    # validate. Tests that specifically exercise poll-template drift can
    # override poll_template_placeholders.
    poll_placeholders = poll_template_placeholders or REQUIRED_PLACEHOLDERS_BY_MODE["poll"]
    poll_body = "# poll template\n" + "\n".join(poll_placeholders) + "\n"
    (builder / "templates" / "agent_poll.py.tmpl").write_text(poll_body, encoding="utf-8")

    agent_md_body = "# {{agent_name}}\n" + "\n".join(EXPECTED_AGENT_MD_SLOTS) + "\n"
    (builder / "templates" / "agent_md.tmpl").write_text(agent_md_body, encoding="utf-8")

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


def test_doctor_reports_recipe_load_ok(tmp_path: Path):
    """Doctor reports OK when the recipes/ subtree is empty but present."""
    registry = _seed_builder(tmp_path)
    recipes_dir = tmp_path / "agent_builder" / "recipes"
    recipes_dir.mkdir()
    for d in ("mcps", "tools", "skills"):
        (recipes_dir / d).mkdir()

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    assert exit_code == 0
    recipe_checks = [c for c in checks if "recipe" in c["name"].lower()]
    assert any(c["status"] == "OK" for c in recipe_checks)


def test_doctor_reports_bad_recipe_fail(tmp_path: Path):
    """Doctor FAILs when a recipe cannot be parsed."""
    registry = _seed_builder(tmp_path)
    broken = tmp_path / "agent_builder" / "recipes" / "tools" / "busted"
    broken.mkdir(parents=True)
    (broken / "RECIPE.md").write_text("no frontmatter", encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    assert exit_code == 1
    assert any(c["status"] == "FAIL" and "recipe" in c["name"].lower() for c in checks)


def test_doctor_warns_when_recipes_dir_missing(tmp_path: Path):
    """Doctor WARNs (not FAILs) when the recipes/ dir is absent."""
    registry = _seed_builder(tmp_path)
    # No recipes dir at all.

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    assert exit_code == 0
    recipe_checks = [c for c in checks if "recipes" in c["name"].lower()]
    assert any(c["status"] == "WARN" for c in recipe_checks)


def test_doctor_validates_poll_template(tmp_path: Path):
    """Poll template drift surfaces as a FAIL with the mode called out in the name."""
    # Seed a builder whose poll template is missing one required placeholder.
    drifted_poll = tuple(
        p for p in REQUIRED_PLACEHOLDERS_BY_MODE["poll"] if p != "{{poll_source_expr}}"
    )
    registry = _seed_builder(tmp_path, poll_template_placeholders=drifted_poll)

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    assert exit_code == 1
    fails = [c for c in checks if c["status"] == "FAIL"]
    assert any("poll" in c["name"] for c in fails), \
        f"expected a FAIL check mentioning 'poll', got: {[c['name'] for c in fails]}"


def test_doctor_fails_on_poll_mode_agent_with_stub_source(tmp_path: Path):
    """A poll-mode agent whose agent.py still calls `_stub_poll_source()` is
    broken on launch (raises NotImplementedError). Doctor must FAIL so the
    user is alerted before they try to run the agent."""
    registry = _seed_builder(tmp_path)
    _make_agent_dir(tmp_path / "output", "broken-poll")
    (tmp_path / "output" / "broken-poll" / "agent.py").write_text(
        "async def main():\n"
        "    poll_source = _stub_poll_source()  # no recipe attached\n",
        encoding="utf-8",
    )
    registry.write_text(json.dumps([
        {"name": "broken-poll", "description": "x", "tools": [], "created": "2026-01-01",
         "path": "output/broken-poll/", "status": "active"},
    ]), encoding="utf-8")

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    assert exit_code == 1
    assert any(
        c["status"] == "FAIL" and "poll_source" in c["name"]
        for c in checks
    )


def test_doctor_validates_both_templates_ok(tmp_path: Path):
    """With both templates well-formed, doctor reports OK for each."""
    registry = _seed_builder(tmp_path)

    checks, exit_code = run_health_check(tmp_path, registry_file=str(registry))
    assert exit_code == 0
    template_oks = [
        c for c in checks
        if c["status"] == "OK" and c["name"].startswith("template:")
    ]
    # One OK per mode.
    assert len(template_oks) == 2
    names = {c["name"] for c in template_oks}
    assert any("agent_main.py.tmpl" in n for n in names)
    assert any("agent_poll.py.tmpl" in n for n in names)
