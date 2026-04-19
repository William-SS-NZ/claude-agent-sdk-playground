"""render_agent — rebuilds agent.py and AGENT.md from an agent's manifest."""

import json
import re
from pathlib import Path

from agent_builder.manifest import Manifest, MANIFEST_FILENAME, load_manifest

TEMPLATES_DIR = Path(__file__).parent / "templates"
_SLOT_PATTERN = re.compile(
    r"<!-- SLOT: (?P<name>\S+) -->(?P<body>.*?)<!-- /SLOT: \S+ -->",
    re.DOTALL,
)

PRESERVED_SLOTS = ("builder_agent_additions", "user_additions")


def render_agent(agent_dir: Path) -> None:
    """Regenerate agent.py + AGENT.md from .recipe_manifest.json."""
    agent_dir = Path(agent_dir)
    manifest_path = agent_dir / MANIFEST_FILENAME
    manifest = load_manifest(manifest_path, agent_name=agent_dir.name)

    _render_agent_py(agent_dir, manifest)
    _render_agent_md(agent_dir, manifest)


def _slug_to_module(slug: str) -> str:
    return slug.replace("-", "_")


def _render_agent_py(agent_dir: Path, manifest: Manifest) -> None:
    agent_py = agent_dir / "agent.py"
    if not agent_py.exists():
        return  # scaffold hasn't written yet; render is a no-op

    content = agent_py.read_text(encoding="utf-8")

    # Build replacement blocks from manifest
    tool_recipes = sorted([r for r in manifest.recipes if r.type == "tool"], key=lambda r: r.name)
    mcp_recipes = sorted([r for r in manifest.recipes if r.type == "mcp"], key=lambda r: r.name)

    imports_lines = []
    server_entries = []
    for r in tool_recipes:
        mod = _slug_to_module(r.name)
        imports_lines.append(
            f"from _recipes.{mod} import tools_server as {mod}_server"
        )
        server_entries.append(f'"{mod}": {mod}_server,')
    imports_block = "\n".join(imports_lines)
    servers_block = "\n            ".join(server_entries)

    # external_mcp_block from mcp-type recipes (reads each recipe's mcp.json via
    # attach-time copy stored alongside _recipes/ as <slug>.mcp.json for renders).
    # Implementation note: attach_recipe copies the mcp.json sibling into
    # agent_dir/_recipes/<slug>.mcp.json so render doesn't need recipe-library access.
    external_entries = []
    for r in mcp_recipes:
        mcp_json = agent_dir / "_recipes" / f"{_slug_to_module(r.name)}.mcp.json"
        if mcp_json.exists():
            cfg = json.loads(mcp_json.read_text(encoding="utf-8"))
            cfg.pop("env_passthrough", None)
            external_entries.append(f'"{_slug_to_module(r.name)}": {repr(cfg)},')
    external_block = "\n            ".join(external_entries)

    pins_dict = {r.name: r.version for r in manifest.recipes}
    pins_block = "RECIPE_PINS = " + json.dumps(dict(sorted(pins_dict.items())))

    # Atomic substitution — all four blocks filled from manifest state.
    content = _replace_block(content, "recipe_imports_block", imports_block)
    content = _replace_block(content, "recipe_servers_block", servers_block)
    content = _replace_block(content, "external_mcp_block", external_block)
    content = _replace_block(content, "recipe_pins_block", pins_block)

    agent_py.write_text(content, encoding="utf-8")


def _replace_block(content: str, block_name: str, new_value: str) -> str:
    """Replace both unfilled {{X}} placeholders AND re-rendered previous values.

    Re-renders stamp a `# <<block_name>>` / `# <</block_name>>` marker pair
    around each block so subsequent renders find and replace them deterministically.
    """
    start_marker = f"# <<{block_name}>>"
    end_marker = f"# <</{block_name}>>"

    block_body = f"{start_marker}\n{new_value}\n{end_marker}"

    placeholder = "{{" + block_name + "}}"
    if placeholder in content:
        return content.replace(placeholder, block_body, 1)

    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    return pattern.sub(block_body, content, count=1)


def _render_agent_md(agent_dir: Path, manifest: Manifest) -> None:
    agent_md = agent_dir / "AGENT.md"
    template_path = TEMPLATES_DIR / "agent_md.tmpl"
    if not template_path.exists():
        return  # Task 0.4 adds this; render is a no-op until then.

    # Preserve the two user-owned slots from the existing AGENT.md.
    preserved: dict[str, str] = {}
    if agent_md.exists():
        existing = agent_md.read_text(encoding="utf-8")
        for m in _SLOT_PATTERN.finditer(existing):
            if m.group("name") in PRESERVED_SLOTS:
                preserved[m.group("name")] = m.group("body")

    template = template_path.read_text(encoding="utf-8")

    # Rendered slots are supplied by skill recipes (Phase G / future); for v0.9
    # every rendered slot is empty unless the agent's authoring step populated it.
    # Phase 0 ships the mechanism; skill-recipe integration is deferred.
    for slot in ("purpose", "workflow", "constraints", "tools_reference", "examples", "first_run_setup"):
        template = template.replace(f"{{{{slot:{slot}}}}}", "")

    for slot in PRESERVED_SLOTS:
        body = preserved.get(slot, "")
        marker_block = f"<!-- SLOT: {slot} -->{body}<!-- /SLOT: {slot} -->"
        template = template.replace(f"{{{{slot:{slot}}}}}", marker_block)

    template = template.replace("{{agent_name}}", manifest.agent_name)
    agent_md.write_text(template, encoding="utf-8")
