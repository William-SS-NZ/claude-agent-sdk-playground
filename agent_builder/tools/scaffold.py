"""scaffold_agent tool — creates agent directory and boilerplate files."""

import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

GITIGNORE_CONTENT = """\
.env
.env.local
__pycache__/
*.py[cod]
CLAUDE.md
"""


def _validate_agent_name(agent_name: str, output_base: str) -> str | None:
    """Validate agent_name and return error message if invalid, None if valid."""
    if not NAME_PATTERN.match(agent_name):
        return f"Invalid agent name '{agent_name}'. Must match ^[a-z0-9][a-z0-9-]*$ (lowercase alphanumeric and hyphens, must start with alphanumeric)."

    if ".." in agent_name or "/" in agent_name or "\\" in agent_name:
        return f"Invalid agent name '{agent_name}'. Must not contain '..', '/', or '\\\\'."

    resolved = (Path(output_base) / agent_name).resolve()
    base_resolved = Path(output_base).resolve()
    if not str(resolved).startswith(str(base_resolved)):
        return f"Invalid agent name '{agent_name}'. Path traversal detected."

    return None


async def scaffold_agent(args: dict[str, Any], output_base: str = "output") -> dict[str, Any]:
    """Create directory structure and boilerplate files for a new agent."""
    agent_name = args["agent_name"]
    description = args["description"]

    error = _validate_agent_name(agent_name, output_base)
    if error:
        return {"content": [{"type": "text", "text": error}], "is_error": True}

    agent_dir = Path(output_base) / agent_name

    if agent_dir.exists():
        return {
            "content": [{"type": "text", "text": f"Directory already exists: {agent_dir}"}],
            "is_error": True,
        }

    agent_dir.mkdir(parents=True)

    # Render agent_main.py template
    template_path = TEMPLATES_DIR / "agent_main.py.tmpl"
    template = template_path.read_text(encoding="utf-8")
    agent_py = template.replace("{{agent_name}}", agent_name)
    (agent_dir / "agent.py").write_text(agent_py, encoding="utf-8")

    # Render .env.example
    env_template_path = TEMPLATES_DIR / "env_example.tmpl"
    env_content = env_template_path.read_text(encoding="utf-8")
    (agent_dir / ".env.example").write_text(env_content, encoding="utf-8")

    # Write .gitignore
    (agent_dir / ".gitignore").write_text(GITIGNORE_CONTENT, encoding="utf-8")

    created_files = ["agent.py", ".env.example", ".gitignore"]
    return {
        "content": [
            {
                "type": "text",
                "text": f"Created agent '{agent_name}' at {agent_dir}/\nFiles: {', '.join(created_files)}\nDescription: {description}",
            }
        ]
    }


# MCP tool registration
scaffold_agent_tool = tool(
    "scaffold_agent",
    "Create the directory structure and boilerplate files for a new agent",
    {"agent_name": str, "description": str},
)(scaffold_agent)
