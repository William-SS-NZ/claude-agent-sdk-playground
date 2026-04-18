"""scaffold_agent tool — creates agent directory and boilerplate files."""

import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder import _version as _builder_version

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Placeholders the scaffold template MUST contain. Single source of truth —
# doctor.py imports this to keep its drift guard in sync with what scaffold
# actually substitutes. Every entry here must appear both in the template
# and in the .replace() chain inside scaffold_agent().
REQUIRED_PLACEHOLDERS = (
    "{{agent_name}}",
    "{{agent_description}}",
    "{{builder_version}}",
    "{{tools_list}}",
    "{{allowed_tools_list}}",
    "{{permission_mode}}",
    "{{max_turns}}",
    "{{max_budget_usd}}",
    "{{cli_args_block}}",
    "{{cli_dispatch_block}}",
    "{{cli_help_epilog}}",
)

GITIGNORE_CONTENT = """\
.env
.env.local
__pycache__/
*.py[cod]
CLAUDE.md
"""


# Inserted into agent_main.py.tmpl when scaffold is called with cli_mode=True.
# Adds --prompt / -p and --spec / -s argparse options. Indented to match the
# template's 4-space indentation inside parser-build.
_CLI_ARGS_BLOCK = '''\
    parser.add_argument(
        "-p", "--prompt",
        help="Non-interactive: send a single prompt and exit after the response.",
    )
    parser.add_argument(
        "-s", "--spec",
        help="Non-interactive: JSON file with {'prompt': '...'} or {'prompts': [...]}.",
    )'''


# Inserted into agent_main.py.tmpl as the argparse epilog when cli_mode=True.
# Describes the JSON shapes accepted by --spec. Rendered with RawTextHelpFormatter
# so the newlines survive to --help output. When cli_mode=False we emit None
# (no epilog needed — there's no --spec flag).
_CLI_HELP_EPILOG = (
    "SPEC FORMAT:\n"
    "  JSON file with one of these shapes:\n"
    "    {\"prompt\": \"single prompt\"}\n"
    "    {\"prompts\": [\"prompt 1\", \"prompt 2\"]}\n"
    "    \"a bare string is also fine\"\n"
)


# Inserted into agent_main.py.tmpl when scaffold is called with cli_mode=True.
# Sits between the ClaudeAgentOptions construction and the chat loop. If the
# user passed --prompt or --spec, runs those prompts and returns before
# entering the interactive loop.
_CLI_DISPATCH_BLOCK = '''\
    cli_prompts = []
    if getattr(args, "prompt", None):
        cli_prompts.append(args.prompt)
    if getattr(args, "spec", None):
        import json as _json
        spec_data = _json.loads(Path(args.spec).read_text(encoding="utf-8"))
        if isinstance(spec_data, str):
            cli_prompts.append(spec_data)
        elif isinstance(spec_data, dict):
            if "prompts" in spec_data:
                cli_prompts.extend(spec_data["prompts"])
            elif "prompt" in spec_data:
                cli_prompts.append(spec_data["prompt"])
    if cli_prompts:
        async with ClaudeSDKClient(options=options) as client:
            for _p in cli_prompts:
                logger.info("cli_prompt: %s", _p)
                await client.query(_p)
                await _drain_responses(client, verbose)
        return
'''


def _validate_agent_name(agent_name: str, output_base: str) -> str | None:
    """Validate agent_name and return error message if invalid, None if valid."""
    if not NAME_PATTERN.match(agent_name):
        return f"Invalid agent name '{agent_name}'. Must match ^[a-z0-9][a-z0-9-]*$ (lowercase alphanumeric and hyphens, must start with alphanumeric)."

    if ".." in agent_name or "/" in agent_name or "\\" in agent_name:
        return f"Invalid agent name '{agent_name}'. Must not contain '..', '/', or '\\\\'."

    resolved = (Path(output_base) / agent_name).resolve()
    base_resolved = Path(output_base).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
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
    cli_mode = bool(args.get("cli_mode", True))

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

    missing_in_template = [p for p in REQUIRED_PLACEHOLDERS if p not in template]
    if missing_in_template:
        return {
            "content": [{"type": "text", "text": (
                f"Template is missing expected placeholders: {missing_in_template}. "
                "This is a builder bug — update agent_main.py.tmpl."
            )}],
            "is_error": True,
        }

    cli_args_block = _CLI_ARGS_BLOCK if cli_mode else ""
    cli_dispatch_block = _CLI_DISPATCH_BLOCK if cli_mode else ""
    # When cli_mode is off there's no --spec to describe; emit None so argparse
    # skips the epilog section entirely. repr() gives us a valid Python literal
    # (triple-quoted / escaped) for either branch.
    cli_help_epilog = repr(_CLI_HELP_EPILOG) if cli_mode else "None"

    # Description is for argparse --help, so escape any quotes
    description_for_help = (description or f"{agent_name} agent").replace('"', '\\"')

    agent_py = (
        template
        .replace("{{agent_name}}", agent_name)
        .replace("{{agent_description}}", description_for_help)
        .replace("{{builder_version}}", _builder_version.__version__)
        .replace("{{tools_list}}", repr(list(tools_list)))
        .replace("{{allowed_tools_list}}", repr(list(allowed_tools_list)))
        .replace("{{permission_mode}}", permission_mode)
        .replace("{{max_turns}}", str(max_turns))
        .replace("{{max_budget_usd}}", f"{max_budget_usd:.2f}")
        .replace("{{cli_args_block}}", cli_args_block)
        .replace("{{cli_dispatch_block}}", cli_dispatch_block)
        .replace("{{cli_help_epilog}}", cli_help_epilog)
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
    "permission_mode: one of 'default', 'acceptEdits', 'bypassPermissions', 'plan', 'dontAsk', 'auto'. "
    "max_turns: safety cap on SDK turns per user message (default 25, raise for iterative agents). "
    "max_budget_usd: per-conversation USD budget cap (default 1.00). "
    "cli_mode: when true (default), the generated agent.py also accepts "
    "-p/--prompt 'text' and -s/--spec file.json for non-interactive runs. "
    "Set false to ship a chat-only agent.",
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
            "cli_mode": {"type": "boolean"},
        },
        "required": ["agent_name", "description"],
    },
)(scaffold_agent)
