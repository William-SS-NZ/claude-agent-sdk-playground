"""Verify the agent_main.py template uses a RotatingFileHandler for log rotation."""

import ast
import logging
from pathlib import Path

from agent_builder.tools.scaffold import TEMPLATES_DIR


def _render_template() -> str:
    """Render agent_main.py.tmpl with representative placeholder values,
    matching the substitution dance in scaffold_agent."""
    template = (TEMPLATES_DIR / "agent_main.py.tmpl").read_text(encoding="utf-8")
    return (
        template
        .replace("{{agent_name}}", "rotation-test")
        .replace("{{agent_description}}", "rotation test agent")
        .replace("{{tools_list}}", repr(["Read", "Edit"]))
        .replace("{{allowed_tools_list}}", repr(["Read", "Edit", "mcp__agent_tools__foo"]))
        .replace("{{permission_mode}}", "acceptEdits")
        .replace("{{max_turns}}", "25")
        .replace("{{max_budget_usd}}", "1.00")
        .replace("{{cli_args_block}}", "")
        .replace("{{cli_dispatch_block}}", "")
    )


def test_rendered_template_imports_rotating_file_handler():
    rendered = _render_template()
    assert "from logging.handlers import RotatingFileHandler" in rendered, (
        "expected `from logging.handlers import RotatingFileHandler` in rendered agent source"
    )


def test_rendered_template_uses_rotating_file_handler():
    rendered = _render_template()
    assert "RotatingFileHandler(" in rendered, (
        "expected RotatingFileHandler to be instantiated in rendered agent source"
    )
    # Plain FileHandler(LOG_PATH, ...) should not be used anymore.
    assert "logging.FileHandler(" not in rendered, (
        "plain logging.FileHandler should have been replaced with RotatingFileHandler"
    )


def test_rendered_template_rotation_settings():
    rendered = _render_template()
    # 5 MB cap.
    assert "5 * 1024 * 1024" in rendered, "expected 5 MB maxBytes setting"
    assert "maxBytes=5 * 1024 * 1024" in rendered, "expected maxBytes=5 * 1024 * 1024 kwarg"
    # 3 rotated backups.
    assert "backupCount=3" in rendered, "expected backupCount=3 kwarg"
    # Encoding preserved.
    assert 'encoding="utf-8"' in rendered, "expected encoding=\"utf-8\" kwarg"


def test_rendered_template_startup_banner_mentions_rotation():
    rendered = _render_template()
    assert "(rotates at 5 MB, keeping 3 backups)" in rendered, (
        "expected startup banner to mention rotation policy"
    )


def test_rendered_template_is_valid_python():
    rendered = _render_template()
    # Must parse — guards against accidental syntax breakage in the template.
    ast.parse(rendered)


def test_rotating_file_handler_actually_rotates(tmp_path: Path):
    """Smoke test: instantiate a RotatingFileHandler with the template's settings
    and confirm writing past the cap produces backup files."""
    log_path = tmp_path / "rotation-test.log"
    # Use a tiny cap for the test so we don't have to write 5 MB.
    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    test_logger = logging.getLogger("agent.rotation-test")
    test_logger.handlers.clear()
    test_logger.setLevel(logging.DEBUG)
    test_logger.addHandler(handler)
    test_logger.propagate = False

    try:
        # Write plenty of bytes to force rotations.
        chunk = "x" * 200
        for _ in range(200):
            test_logger.info(chunk)
        handler.flush()

        # At least one backup should exist.
        backup1 = tmp_path / "rotation-test.log.1"
        assert log_path.exists(), "primary log file should still exist"
        assert backup1.exists(), "expected at least one rotated backup (.log.1)"
    finally:
        handler.close()
        test_logger.handlers.clear()
