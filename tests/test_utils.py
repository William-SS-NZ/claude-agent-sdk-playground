import pytest
from pathlib import Path
from agent_builder.utils import build_claude_md


def test_build_claude_md_creates_file(tmp_agent_dir: Path):
    source = str(tmp_agent_dir / "identity")
    output = str(tmp_agent_dir)

    build_claude_md(source_dir=source, output_dir=output)

    claude_md = tmp_agent_dir / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in content
    assert "# Agent" in content
    assert "You are a test agent." in content
    assert "# Soul" in content
    assert "Be helpful and concise." in content
    assert "# Memory" in content
    assert "No prior context." in content


def test_build_claude_md_skips_missing_user_md(tmp_agent_dir: Path):
    source = str(tmp_agent_dir / "identity")
    output = str(tmp_agent_dir)

    build_claude_md(source_dir=source, output_dir=output)

    content = (tmp_agent_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# User" not in content


def test_build_claude_md_includes_user_md_when_present(tmp_agent_dir_with_user: Path):
    source = str(tmp_agent_dir_with_user / "identity")
    output = str(tmp_agent_dir_with_user)

    build_claude_md(source_dir=source, output_dir=output)

    content = (tmp_agent_dir_with_user / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# User" in content
    assert "Name: William" in content


def test_build_claude_md_verbose_output(tmp_agent_dir: Path, capsys: pytest.CaptureFixture[str]):
    source = str(tmp_agent_dir / "identity")
    output = str(tmp_agent_dir)

    build_claude_md(source_dir=source, output_dir=output, verbose=True)

    captured = capsys.readouterr()
    assert "[build_claude_md] Found:" in captured.out
    assert "AGENT.md" in captured.out
    assert "Wrote CLAUDE.md" in captured.out


def test_build_claude_md_overwrites_existing(tmp_agent_dir: Path):
    output = str(tmp_agent_dir)
    claude_md = tmp_agent_dir / "CLAUDE.md"
    claude_md.write_text("old content", encoding="utf-8")

    build_claude_md(source_dir=str(tmp_agent_dir / "identity"), output_dir=output)

    content = claude_md.read_text(encoding="utf-8")
    assert "old content" not in content
    assert "AUTO-GENERATED" in content
