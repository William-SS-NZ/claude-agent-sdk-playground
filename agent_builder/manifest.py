"""Agent manifest — source of truth for attached recipes and components."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MANIFEST_FILENAME = ".recipe_manifest.json"
CURRENT_MANIFEST_VERSION = 1


class ManifestError(ValueError):
    """Raised on malformed or incompatible manifests."""


@dataclass
class AttachedRecipe:
    name: str
    type: str           # "tool" | "mcp" | "skill"
    version: str
    attached_at: str    # ISO date (YYYY-MM-DD)
    git_sha: str = ""   # short 7-char hash, optional


@dataclass
class AttachedComponent:
    name: str
    version: str
    target: str         # e.g. "agent.py" | "tools.py" | "AGENT.md:slot=workflow"
    attached_at: str
    git_sha: str = ""


@dataclass
class Manifest:
    manifest_version: int = CURRENT_MANIFEST_VERSION
    agent_name: str = ""
    builder_version: str = ""
    recipes: list[AttachedRecipe] = field(default_factory=list)
    components: list[AttachedComponent] = field(default_factory=list)
    # Name of the attached recipe that supplies the poll-source async generator.
    # Empty string when the agent runs in CLI mode or no poll recipe is attached.
    # Exactly one recipe may claim this slot — attach_recipe enforces.
    poll_source: str = ""


def empty_manifest(agent_name: str, builder_version: str) -> Manifest:
    return Manifest(agent_name=agent_name, builder_version=builder_version)


def load_manifest(path: Path, *, agent_name: str = "", builder_version: str = "") -> Manifest:
    path = Path(path)
    if not path.exists():
        return empty_manifest(agent_name=agent_name, builder_version=builder_version)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ManifestError(f"{path}: not valid JSON: {e}") from e

    if data.get("manifest_version") != CURRENT_MANIFEST_VERSION:
        raise ManifestError(
            f"{path}: manifest_version {data.get('manifest_version')!r} not supported "
            f"(this builder expects {CURRENT_MANIFEST_VERSION})"
        )

    recipes = [AttachedRecipe(**r) for r in data.get("recipes", [])]
    _check_unique(recipes, "recipe", path)
    components = [AttachedComponent(**c) for c in data.get("components", [])]
    _check_unique(components, "component", path)

    return Manifest(
        manifest_version=data["manifest_version"],
        agent_name=data.get("agent_name", ""),
        builder_version=data.get("builder_version", ""),
        recipes=recipes,
        components=components,
        # Tolerate pre-existing manifests without the field — default to empty.
        poll_source=data.get("poll_source", "") or "",
    )


def save_manifest(path: Path, manifest: Manifest) -> None:
    path = Path(path)
    data = asdict(manifest)
    # Sort recipes + components alphabetically for stable diffs.
    data["recipes"] = sorted(data["recipes"], key=lambda r: r["name"])
    data["components"] = sorted(data["components"], key=lambda c: (c["target"], c["name"]))
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _check_unique(items: list, label: str, path: Path) -> None:
    seen: set[str] = set()
    for item in items:
        key = getattr(item, "name")
        if label == "component":
            key = f"{item.target}::{item.name}"
        if key in seen:
            raise ManifestError(f"{path}: duplicate {label} {key!r}")
        seen.add(key)
