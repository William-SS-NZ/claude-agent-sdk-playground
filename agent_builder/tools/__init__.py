"""Builder tools — bundled into a single MCP server."""

from claude_agent_sdk import create_sdk_mcp_server

from agent_builder.tools.scaffold import scaffold_agent_tool
from agent_builder.tools.write_identity import write_identity_tool
from agent_builder.tools.write_tools import write_tools_tool
from agent_builder.tools.test_agent import test_agent_tool
from agent_builder.tools.registry import registry_tool
from agent_builder.tools.remove_agent import remove_agent_tool
from agent_builder.tools.self_heal import propose_self_change_tool

builder_tools_server = create_sdk_mcp_server(
    name="builder_tools",
    version="1.0.0",
    tools=[
        scaffold_agent_tool,
        write_identity_tool,
        write_tools_tool,
        test_agent_tool,
        registry_tool,
        remove_agent_tool,
        propose_self_change_tool,
    ],
)
