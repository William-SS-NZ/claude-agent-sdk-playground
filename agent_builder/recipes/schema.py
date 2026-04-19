"""Recipe frontmatter schema, dataclasses, and validation."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml


class RecipeError(ValueError):
    """Raised when a recipe's RECIPE.md is malformed or invalid."""


class RecipeType(str, Enum):
    MCP = "mcp"
    TOOL = "tool"
    SKILL = "skill"


_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_FRONTMATTER_PATTERN = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z",
    re.DOTALL,
)


@dataclass(frozen=True)
class EnvKey:
    name: str
    description: str
    example: str = ""


@dataclass(frozen=True)
class Recipe:
    name: str
    type: RecipeType
    version: str
    description: str
    when_to_use: str
    env_keys: list[EnvKey] = field(default_factory=list)
    oauth_scopes: list[str] = field(default_factory=list)
    allowed_tools_patterns: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    body: str = ""
    source_path: str = ""


def parse_recipe_md(content: str, *, source_path: str) -> Recipe:
    """Parse a RECIPE.md file's raw content into a Recipe dataclass.

    Raises RecipeError on any schema violation so the caller can surface
    a clear error message pointing at the source file.
    """
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        raise RecipeError(
            f"{source_path}: missing or malformed frontmatter (expected --- ... --- at start of file)"
        )
    try:
        data: Any = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise RecipeError(f"{source_path}: frontmatter is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise RecipeError(f"{source_path}: frontmatter must be a mapping, got {type(data).__name__}")

    body = match.group(2)

    _require_keys(data, ("name", "type", "version", "description", "when_to_use"), source_path)

    name = data["name"]
    if not isinstance(name, str) or not _NAME_PATTERN.match(name):
        raise RecipeError(
            f"{source_path}: name '{name}' invalid (must match ^[a-z0-9][a-z0-9-]*$)"
        )

    try:
        type_ = RecipeType(data["type"])
    except ValueError:
        raise RecipeError(
            f"{source_path}: type '{data['type']}' invalid (must be one of: {[t.value for t in RecipeType]})"
        ) from None

    version = data["version"]
    if not isinstance(version, str) or not _SEMVER_PATTERN.match(version):
        raise RecipeError(
            f"{source_path}: version '{version}' invalid (must be semver like '0.1.0')"
        )

    description = _require_str(data, "description", source_path)
    when_to_use = _require_str(data, "when_to_use", source_path)

    env_keys = _parse_env_keys(data.get("env_keys", []), source_path)
    oauth_scopes = _parse_string_list(data.get("oauth_scopes", []), "oauth_scopes", source_path)
    allowed_tools_patterns = _parse_string_list(
        data.get("allowed_tools_patterns", []), "allowed_tools_patterns", source_path
    )
    tags = _parse_string_list(data.get("tags", []), "tags", source_path)

    return Recipe(
        name=name,
        type=type_,
        version=version,
        description=description,
        when_to_use=when_to_use,
        env_keys=env_keys,
        oauth_scopes=oauth_scopes,
        allowed_tools_patterns=allowed_tools_patterns,
        tags=tags,
        body=body,
        source_path=source_path,
    )


def _require_keys(data: dict, keys: tuple[str, ...], source_path: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise RecipeError(f"{source_path}: frontmatter missing required keys: {missing}")


def _require_str(data: dict, key: str, source_path: str) -> str:
    v = data[key]
    if not isinstance(v, str) or not v.strip():
        raise RecipeError(f"{source_path}: '{key}' must be a non-empty string")
    return v


def _parse_string_list(value: Any, field_name: str, source_path: str) -> list[str]:
    if value in (None, []):
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise RecipeError(f"{source_path}: '{field_name}' must be a list of strings")
    return list(value)


def _parse_env_keys(value: Any, source_path: str) -> list[EnvKey]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise RecipeError(f"{source_path}: 'env_keys' must be a list")
    out: list[EnvKey] = []
    for i, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise RecipeError(f"{source_path}: env_keys[{i}] must be a mapping")
        if "name" not in entry or "description" not in entry:
            raise RecipeError(f"{source_path}: env_keys[{i}] missing 'name' or 'description'")
        out.append(EnvKey(
            name=str(entry["name"]),
            description=str(entry["description"]),
            example=str(entry.get("example", "")),
        ))
    return out
