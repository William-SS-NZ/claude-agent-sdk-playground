import shutil
from pathlib import Path

import pytest

from agent_builder.tools import self_heal
from agent_builder.tools.self_heal import propose_self_change, _validate_target


@pytest.fixture
def sandbox_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mirror agent_builder/ into a tmp dir and redirect self_heal to it."""
    fake_builder = tmp_path / "agent_builder"
    fake_builder.mkdir()
    (fake_builder / "identity").mkdir()
    (fake_builder / "tools").mkdir()
    (fake_builder / "templates").mkdir()
    (fake_builder / "registry").mkdir()

    (fake_builder / "identity" / "AGENT.md").write_text("# Agent\nPhase 1.\n", encoding="utf-8")
    (fake_builder / "utils.py").write_text("# utils\n", encoding="utf-8")
    (fake_builder / "tools" / "scaffold.py").write_text("def x(): pass\n", encoding="utf-8")
    (fake_builder / "registry" / "agents.json").write_text("[]", encoding="utf-8")

    monkeypatch.setattr(self_heal, "BUILDER_DIR", fake_builder.resolve())
    monkeypatch.setattr(self_heal, "AUDIT_LOG_PATH", fake_builder / "self-heal.log")
    # Reset logger handlers so it writes into the sandbox
    monkeypatch.setattr(self_heal, "_audit_logger",
                        self_heal._audit_logger)  # keep reference, but redirect via handler swap below
    for h in list(self_heal._audit_logger.handlers):
        self_heal._audit_logger.removeHandler(h)
    import logging
    fh = logging.FileHandler(fake_builder / "self-heal.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    self_heal._audit_logger.addHandler(fh)

    return fake_builder


# --- Validator tests ---

def test_validate_rejects_absolute_path(sandbox_builder: Path):
    _, err = _validate_target("/tmp/evil")
    assert err and "absolute" in err.lower()


def test_validate_rejects_escape(sandbox_builder: Path):
    _, err = _validate_target("../outside.md")
    assert err and ("escapes" in err or "not in whitelist" in err)


def test_validate_rejects_registry(sandbox_builder: Path):
    _, err = _validate_target("registry/agents.json")
    assert err and "deny" in err.lower()


def test_validate_accepts_identity(sandbox_builder: Path):
    path, err = _validate_target("identity/AGENT.md")
    assert err is None
    assert path is not None and path.name == "AGENT.md"


def test_validate_accepts_tools_subdir(sandbox_builder: Path):
    path, err = _validate_target("tools/scaffold.py")
    assert err is None


def test_validate_accepts_utils_top_level(sandbox_builder: Path):
    path, err = _validate_target("utils.py")
    assert err is None


def test_validate_rejects_tests_dir(sandbox_builder: Path):
    _, err = _validate_target("tests/test_foo.py")
    assert err and "not in whitelist" in err


# --- Apply / decline tests ---

@pytest.mark.asyncio
async def test_declined_change_leaves_file_unchanged(sandbox_builder: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(self_heal, "_prompt_confirm", _fake_no)
    target = sandbox_builder / "identity" / "AGENT.md"
    original = target.read_text(encoding="utf-8")

    result = await propose_self_change({
        "target_path": "identity/AGENT.md",
        "summary": "Add phase 2",
        "why": "Was missing.",
        "before_snippet": "Phase 1.",
        "after_snippet": "Phase 1.\nPhase 2.",
        "old_string": "Phase 1.\n",
        "new_string": "Phase 1.\nPhase 2.\n",
    })

    assert "is_error" not in result
    assert "declined" in result["content"][0]["text"].lower()
    assert target.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_approved_change_applies_and_backs_up(sandbox_builder: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(self_heal, "_prompt_confirm", _fake_yes)
    target = sandbox_builder / "identity" / "AGENT.md"

    result = await propose_self_change({
        "target_path": "identity/AGENT.md",
        "summary": "Add phase 2",
        "why": "Was missing.",
        "before_snippet": "Phase 1.",
        "after_snippet": "Phase 1.\nPhase 2.",
        "old_string": "Phase 1.\n",
        "new_string": "Phase 1.\nPhase 2.\n",
    })

    assert "is_error" not in result
    assert "Phase 2." in target.read_text(encoding="utf-8")
    backups = list(target.parent.glob("AGENT.md.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "# Agent\nPhase 1.\n"


@pytest.mark.asyncio
async def test_old_string_not_found_is_error(sandbox_builder: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(self_heal, "_prompt_confirm", _fake_yes)

    result = await propose_self_change({
        "target_path": "identity/AGENT.md",
        "summary": "x",
        "why": "y",
        "before_snippet": "a",
        "after_snippet": "b",
        "old_string": "not_in_file",
        "new_string": "whatever",
    })

    assert result.get("is_error") is True
    assert "old_string not found" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_ambiguous_old_string_is_error(sandbox_builder: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(self_heal, "_prompt_confirm", _fake_yes)
    # Make "# utils" appear twice so replacement is ambiguous
    utils = sandbox_builder / "utils.py"
    utils.write_text("# utils\n# utils\n", encoding="utf-8")

    result = await propose_self_change({
        "target_path": "utils.py",
        "summary": "x",
        "why": "y",
        "before_snippet": "a",
        "after_snippet": "b",
        "old_string": "# utils\n",
        "new_string": "# renamed\n",
    })

    assert result.get("is_error") is True
    assert "ambiguous" in result["content"][0]["text"] or "multiple" in result["content"][0]["text"].lower() or "2 places" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_missing_change_payload_is_error(sandbox_builder: Path):
    result = await propose_self_change({
        "target_path": "identity/AGENT.md",
        "summary": "x",
        "why": "y",
    })
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_rejects_output_path(sandbox_builder: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(self_heal, "_prompt_confirm", _fake_yes)
    result = await propose_self_change({
        "target_path": "../output/evil/agent.py",
        "summary": "x",
        "why": "y",
        "old_string": "a",
        "new_string": "b",
    })
    assert result.get("is_error") is True


# --- helpers ---

async def _fake_yes():
    return True


async def _fake_no():
    return False
