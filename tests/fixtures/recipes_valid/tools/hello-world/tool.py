"""Hello world tool — test fixture."""

from claude_agent_sdk import tool, create_sdk_mcp_server


@tool("hello", "Returns a greeting.", {"type": "object", "properties": {"name": {"type": "string"}}})
async def hello(args):
    if TEST_MODE:  # noqa: F821 — prepended by write_tools
        return {"content": [{"type": "text", "text": "hello test"}]}
    return {"content": [{"type": "text", "text": f"hello {args.get('name', 'world')}"}]}


tools_server = create_sdk_mcp_server(name="hello-tools", version="0.1.0", tools=[hello])
