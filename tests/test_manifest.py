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
