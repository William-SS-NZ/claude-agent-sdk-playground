"""scaffold_agent tool — creates agent directory and boilerplate files."""

import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from agent_builder import _version as _builder_version
from agent_builder.manifest import MANIFEST_FILENAME, empty_manifest, save_manifest
from agent_builder.paths import validate_relative_to_base

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Mode -> template filename. "server" mode arrives in Phase F.
_TEMPLATE_BY_MODE = {
    "cli": "agent_main.py.tmpl",
    "poll": "agent_poll.py.tmpl",
}

# Stubs filled when no recipe supplies poll_source. Keeps generated agents
# syntactically valid so they can be run (will raise NotImplementedError when
# the poll loop starts, with a helpful message).
_POLL_SOURCE_IMPORT_STUB = ""
_POLL_SOURCE_EXPR_STUB = (
    "_stub_poll_source()  # attach a poll recipe (e.g. telegram-poll) to replace this"
)
_POLL_SOURCE_STUB_IMPL = '''
async def _stub_poll_source():
    raise NotImplementedError(
        "No poll source attached. Run: python -m agent_builder.builder "
        "then attach_recipe for this agent with a poll-type recipe."
    )
    yield  # pragma: no cover — make this a generator
'''

# Placeholders common to every template.
REQUIRED_PLACEHOLDERS_COMMON = (
    "{{agent_name}}",
    "{{agent_description}}",
    "{{builder_version}}",
    "{{recipe_pins_block}}",
    "{{tools_list}}",
    "{{allowed_tools_list}}",
    "{{permission_mode}}",
    "{{max_turns}}",
    "{{max_budget_usd}}",
    "{{recipe_imports_block}}",
    "{{recipe_servers_block}}",
    "{{external_mcp_block}}",
)

# Mode-specific placeholders. Doctor imports REQUIRED_PLACEHOLDERS_BY_MODE
# to run the drift guard over every template.
REQUIRED_PLACEHOLDERS_BY_MODE = {
    "cli": REQUIRED_PLACEHOLDERS_COMMON + (
        "{{cli_args_block}}",
        "{{cli_dispatch_block}}",
        "{{cli_help_epilog}}",
    ),
    "poll": REQUIRED_PLACEHOLDERS_COMMON + (
        "{{poll_source_import}}",
        "{{poll_source_expr}}",
    ),
}

# Back-compat alias — doctor.py still imports REQUIRED_PLACEHOLDERS, and the
# scaffold template drift guard in test_scaffold.py references it.
REQUIRED_PLACEHOLDERS = REQUIRED_PLACEHOLDERS_BY_MODE["cli"]

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
    """Validate agent_name and return error message if invalid, None if valid.

    The slug-regex check and the "no ``..``/``/``/``\\\\`` in the name" check
    are scaffold-specific (agent names must be clean, human-readable slugs).
    The "does this path land inside output_base?" check delegates to the
    shared ``validate_relative_to_base`` helper — same logic the other three
    tools use.
    """
    if not NAME_PATTERN.match(agent_name):
        return f"Invalid agent name '{agent_name}'. Must match ^[a-z0-9][a-z0-9-]*$ (lowercase alphanumeric and hyphens, must start with alphanumeric)."

    if ".." in agent_name or "/" in agent_name or "\\" in agent_name:
        return f"Invalid agent name '{agent_name}'. Must not contain '..', '/', or '\\\\'."

    _, err = validate_relative_to_base(
        str(Path(output_base) / agent_name),
        [Path(output_base)],
    )
    if err is not None:
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
    mode = args.get("mode", "cli")

    if mode not in _TEMPLATE_BY_MODE:
        return {
            "content": [{"type": "text", "text": (
                f"Invalid mode '{mode}'. Allowed: {sorted(_TEMPLATE_BY_MODE)}."
            )}],
            "is_error": True,
        }

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

    # Render agent entrypoint template (varies by mode).
    template_path = TEMPLATES_DIR / _TEMPLATE_BY_MODE[mode]
    template = template_path.read_text(encoding="utf-8")

    expected_placeholders = REQUIRED_PLACEHOLDERS_BY_MODE[mode]
    missing_in_template = [p for p in expected_placeholders if p not in template]
    if missing_in_template:
        return {
            "content": [{"type": "text", "text": (
                f"Template is missing expected placeholders: {missing_in_template}. "
                f"This is a builder bug — update {_TEMPLATE_BY_MODE[mode]}."
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

    # For poll mode, inject the _stub_poll_source() helper above `# --- Main ---`
    # so the generated agent runs without NameError before a real poll recipe is
    # attached. Must happen BEFORE the placeholder .replace() chain so the stub
    # body doesn't accidentally interact with substitutions.
    if mode == "poll":
        template = template.replace(
            "# --- Main ---",
            _POLL_SOURCE_STUB_IMPL + "\n# --- Main ---",
            1,
        )

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
        .replace("{{recipe_imports_block}}", "# <<recipe_imports_block>>\n# <</recipe_imports_block>>")
        .replace("{{recipe_servers_block}}", "# <<recipe_servers_block>>\n            # <</recipe_servers_block>>")
        .replace("{{external_mcp_block}}", "# <<external_mcp_block>>\n            # <</external_mcp_block>>")
        .replace("{{recipe_pins_block}}", "# <<recipe_pins_block>>\nRECIPE_PINS = {}\n# <</recipe_pins_block>>")
    )

    if mode == "poll":
        agent_py = (
            agent_py
            .replace("{{poll_source_import}}", _POLL_SOURCE_IMPORT_STUB)
            .replace("{{poll_source_expr}}", _POLL_SOURCE_EXPR_STUB)
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

    # Seed an empty .recipe_manifest.json so later attach_recipe calls have
    # a file to read and render_agent can reconstitute the agent deterministically.
    save_manifest(
        agent_dir / MANIFEST_FILENAME,
        empty_manifest(agent_name=agent_name, builder_version=_builder_version.__version__),
    )

    created_files = ["agent.py", ".env.example", ".gitignore", MANIFEST_FILENAME]
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
    "Set false to ship a chat-only agent. "
    "mode: 'cli' (default) for interactive / CLI agents, 'poll' for long-poll "
    "workers that react to an incoming-message stream (e.g. Telegram).",
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
            "mode": {"type": "string", "enum": ["cli", "poll"]},
        },
        "required": ["agent_name", "description"],
    },
)(scaffold_agent)
