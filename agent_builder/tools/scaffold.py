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
    tools_list = args.get("tools_list", ["Read", "Glob", "Grep"])
    allowed_tools_list = args.get("allowed_tools_list", list(tools_list))
    permission_mode = args.get("permission_mode", "acceptEdits")
    max_turns = int(args.get("max_turns", 25))
    max_budget_usd = float(args.get("max_budget_usd", 1.00))

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
    agent_py = (
        template
        .replace("{{agent_name}}", agent_name)
        .replace("{{tools_list}}", repr(list(tools_list)))
        .replace("{{allowed_tools_list}}", repr(list(allowed_tools_list)))
        .replace("{{permission_mode}}", permission_mode)
        .replace("{{max_turns}}", str(max_turns))
        .replace("{{max_budget_usd}}", f"{max_budget_usd:.2f}")
    )

    # Fail loudly if any placeholder survived — the generated agent.py would
    # be invalid Python and fail with NameError on first run otherwise.
    unfilled = re.findall(r"\{\{[^}]+\}\}", agent_py)
    if unfilled:
        return {
            "content": [{"type": "text", "text": (
                f"Template has unfilled placeholders after substitution: {sorted(set(unfilled))}. "
                "This is a builder bug — update scaffold_agent to fill them."
            )}],
            "is_error": True,
        }

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
    "Create the directory structure and boilerplate files for a new agent. "
    "tools_list: builtin tool names (e.g. ['Read','Edit','Bash']). "
    "allowed_tools_list: full allowed list including mcp__agent_tools__* entries. "
    "permission_mode: 'default', 'acceptEdits', 'bypassPermissions', or 'plan'. "
    "max_turns: safety cap on SDK turns per user message (default 25, raise for iterative agents). "
    "max_budget_usd: per-conversation USD budget cap (default 1.00).",
    {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string"},
            "description": {"type": "string"},
            "tools_list": {"type": "array", "items": {"type": "string"}},
            "allowed_tools_list": {"type": "array", "items": {"type": "string"}},
            "permission_mode": {"type": "string"},
            "max_turns": {"type": "integer"},
            "max_budget_usd": {"type": "number"},
        },
        "required": ["agent_name", "description"],
    },
)(scaffold_agent)
