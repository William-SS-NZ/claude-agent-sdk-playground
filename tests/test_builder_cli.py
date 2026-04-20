"""Tests for the builder.py CLI spec loader + phase banner helpers."""

import json
from pathlib import Path

import pytest

from agent_builder import builder as builder_mod


def test_load_spec_prompts_list(tmp_path: Path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"prompts": ["first", "second"]}), encoding="utf-8")
    assert builder_mod._load_spec(str(p)) == ["first", "second"]


def test_load_spec_single_prompt(tmp_path: Path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"prompt": "hi"}), encoding="utf-8")
    assert builder_mod._load_spec(str(p)) == ["hi"]


def test_load_spec_bare_string(tmp_path: Path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps("just a string"), encoding="utf-8")
    assert builder_mod._load_spec(str(p)) == ["just a string"]


def test_load_spec_missing_key_raises(tmp_path: Path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"other": "thing"}), encoding="utf-8")
    with pytest.raises(ValueError, match="'prompt'"):
        builder_mod._load_spec(str(p))


def test_load_spec_prompts_not_a_list_raises(tmp_path: Path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"prompts": "nope"}), encoding="utf-8")
    with pytest.raises(ValueError, match="list of strings"):
        builder_mod._load_spec(str(p))


def test_phase_label_for_known_tool():
    label = builder_mod._phase_label_for("mcp__builder_tools__scaffold_agent")
    assert "Phase 4" in label and "scaffolding" in label


def test_phase_label_for_unknown_tool():
    label = builder_mod._phase_label_for("SomethingWeird")
    assert label == "running SomethingWeird"


def test_phase_banner_fires_once_per_tool():
    seen: set[str] = set()
    first = builder_mod._phase_banner("mcp__builder_tools__test_agent", seen)
    second = builder_mod._phase_banner("mcp__builder_tools__test_agent", seen)
    assert first is not None and "Phase 5" in first
    assert second is None


def test_setup_run_logger_creates_timestamped_file(tmp_path: Path, monkeypatch):
    """Each builder invocation gets its own builder-YYYYMMDD-HHMMSS.log."""
    monkeypatch.setattr(builder_mod, "LOGS_DIR", tmp_path / "logs")

    logger, log_path = builder_mod._setup_run_logger()

    assert log_path.parent == tmp_path / "logs"
    assert log_path.name.startswith("builder-")
    assert log_path.name.endswith(".log")
    # Stamp portion: builder-YYYYMMDD-HHMMSS.log → 15-char stamp
    stamp = log_path.stem.removeprefix("builder-")
    assert len(stamp) == 15  # YYYYMMDD-HHMMSS
    assert stamp[8] == "-"

    logger.info("hello")
    for h in logger.handlers:
        h.flush()
    assert "hello" in log_path.read_text(encoding="utf-8")


def test_setup_run_logger_isolates_runs(tmp_path: Path, monkeypatch):
    """Two runs in the same process get different files (no shared handler)."""
    import time as _time
    monkeypatch.setattr(builder_mod, "LOGS_DIR", tmp_path / "logs")

    _l1, p1 = builder_mod._setup_run_logger()
    _time.sleep(1.05)  # tick the second so timestamps differ
    _l2, p2 = builder_mod._setup_run_logger()

    assert p1 != p2


def test_web_tools_off_by_default(monkeypatch):
    """WebFetch/WebSearch must be gated — off unless ENABLE_WEB_TOOLS=1."""
    monkeypatch.delenv("ENABLE_WEB_TOOLS", raising=False)
    opts = builder_mod._build_options()
    assert "WebFetch" not in opts.allowed_tools
    assert "WebSearch" not in opts.allowed_tools


def test_web_tools_on_when_env_set(monkeypatch):
    """Setting ENABLE_WEB_TOOLS=1 opts the builder into web research."""
    monkeypatch.setenv("ENABLE_WEB_TOOLS", "1")
    opts = builder_mod._build_options()
    assert "WebFetch" in opts.allowed_tools
    assert "WebSearch" in opts.allowed_tools


def test_web_tools_off_when_env_set_to_other_value(monkeypatch):
    """Only the literal '1' enables — other truthy-ish values stay off."""
    monkeypatch.setenv("ENABLE_WEB_TOOLS", "0")
    opts = builder_mod._build_options()
    assert "WebFetch" not in opts.allowed_tools
    assert "WebSearch" not in opts.allowed_tools


# --- Menu tests ---

def test_menu_text_lists_all_choices():
    text = builder_mod._menu_text()
    for key, (label, _) in builder_mod._MENU_CHOICES.items():
        assert f"{key}. {label}" in text
    assert "exit" in text
    assert "menu" in text


def test_expand_menu_choice_returns_seed_for_known_numbers():
    seed = builder_mod._expand_menu_choice("1")
    assert seed is not None
    assert "build" in seed.lower() or "phase 1" in seed.lower()

    seed = builder_mod._expand_menu_choice("5")
    assert seed is not None
    assert "remove" in seed.lower()


def test_expand_menu_choice_returns_none_for_freeform_input():
    assert builder_mod._expand_menu_choice("build me a markdown bot") is None
    assert builder_mod._expand_menu_choice("make a thing") is None


def test_expand_menu_choice_returns_none_for_option_7_freeform():
    """Option 7 is 'something else — I'll describe it', empty seed by design."""
    assert builder_mod._expand_menu_choice("7") is None


def test_expand_menu_choice_strips_whitespace():
    assert builder_mod._expand_menu_choice("  3  ") is not None


def test_expand_menu_choice_returns_none_for_unknown_number():
    assert builder_mod._expand_menu_choice("99") is None
    assert builder_mod._expand_menu_choice("0") is None


def test_registered_agent_names_empty_when_registry_missing(tmp_path: Path, monkeypatch):
    """Short-circuit for menu options 2-6 relies on this returning []."""
    monkeypatch.setattr(builder_mod, "_REGISTRY_PATH", str(tmp_path / "nope.json"))
    assert builder_mod._registered_agent_names() == []


def test_registered_agent_names_reads_registered(tmp_path: Path, monkeypatch):
    p = tmp_path / "agents.json"
    p.write_text('[{"name": "alpha"}, {"name": "beta"}]', encoding="utf-8")
    monkeypatch.setattr(builder_mod, "_REGISTRY_PATH", str(p))
    assert builder_mod._registered_agent_names() == ["alpha", "beta"]


def test_registered_agent_names_tolerates_corrupt_registry(tmp_path: Path, monkeypatch):
    p = tmp_path / "agents.json"
    p.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(builder_mod, "_REGISTRY_PATH", str(p))
    assert builder_mod._registered_agent_names() == []
