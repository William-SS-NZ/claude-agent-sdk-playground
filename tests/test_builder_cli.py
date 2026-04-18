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
