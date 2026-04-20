"""Tests for .recipe_manifest.json read/write/merge."""

import json
from pathlib import Path

import pytest

from agent_builder.manifest import (
    Manifest,
    ManifestError,
    load_manifest,
    save_manifest,
    empty_manifest,
)


def test_empty_manifest_roundtrips(tmp_path):
    m = empty_manifest(agent_name="x", builder_version="0.9.0")
    save_manifest(tmp_path / ".recipe_manifest.json", m)
    loaded = load_manifest(tmp_path / ".recipe_manifest.json")
    assert loaded.agent_name == "x"
    assert loaded.builder_version == "0.9.0"
    assert loaded.recipes == []
    assert loaded.components == []


def test_manifest_rejects_bad_shape(tmp_path):
    (tmp_path / ".recipe_manifest.json").write_text('{"manifest_version": 99}', encoding="utf-8")
    with pytest.raises(ManifestError, match="manifest_version"):
        load_manifest(tmp_path / ".recipe_manifest.json")


def test_manifest_rejects_duplicate_recipe_names(tmp_path):
    bad = {
        "manifest_version": 1,
        "agent_name": "x",
        "builder_version": "0.9.0",
        "recipes": [
            {"name": "telegram-poll", "type": "tool", "version": "0.1.0", "attached_at": "2026-04-20"},
            {"name": "telegram-poll", "type": "tool", "version": "0.2.0", "attached_at": "2026-04-20"},
        ],
        "components": [],
    }
    (tmp_path / ".recipe_manifest.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ManifestError, match="duplicate"):
        load_manifest(tmp_path / ".recipe_manifest.json")


def test_manifest_missing_file_returns_empty(tmp_path):
    m = load_manifest(tmp_path / "nonexistent.json", agent_name="x", builder_version="0.9.0")
    assert m.recipes == []


def test_manifest_poll_source_roundtrips(tmp_path):
    m = empty_manifest(agent_name="x", builder_version="0.9.0")
    m.poll_source = "telegram-poll"
    save_manifest(tmp_path / ".recipe_manifest.json", m)
    loaded = load_manifest(tmp_path / ".recipe_manifest.json")
    assert loaded.poll_source == "telegram-poll"


def test_manifest_poll_source_default_empty(tmp_path):
    m = empty_manifest(agent_name="x", builder_version="0.9.0")
    assert m.poll_source == ""
    save_manifest(tmp_path / ".recipe_manifest.json", m)
    loaded = load_manifest(tmp_path / ".recipe_manifest.json")
    assert loaded.poll_source == ""


def test_save_manifest_is_atomic(tmp_path):
    """save_manifest writes via tmp + os.replace so readers never see a partial
    file. After a successful save, the .tmp sibling must not linger."""
    target = tmp_path / ".recipe_manifest.json"
    m = empty_manifest(agent_name="x", builder_version="0.9.0")
    save_manifest(target, m)
    assert target.exists()
    assert not (tmp_path / ".recipe_manifest.json.tmp").exists()


def test_manifest_load_tolerates_missing_poll_source_field(tmp_path):
    # Pre-existing manifest written without the poll_source field should load cleanly.
    raw = {
        "manifest_version": 1,
        "agent_name": "x",
        "builder_version": "0.9.0",
        "recipes": [],
        "components": [],
    }
    (tmp_path / ".recipe_manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    loaded = load_manifest(tmp_path / ".recipe_manifest.json")
    assert loaded.poll_source == ""
