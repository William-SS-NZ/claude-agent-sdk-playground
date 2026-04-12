"""
test_bot — a read-only Notion agent.

Connects to the official Notion MCP server and restricts to read-only
operations (search, fetch, get). Write tools are explicitly disallowed.

Setup:
  1. Create a Notion integration at https://www.notion.so/my-integrations
  2. Copy the integration token
  3. Set env var:  export NOTION_TOKEN="ntn_your_token_here"
  4. Share the Notion pages/databases you want the bot to access
     with your integration (click ··· > Connections > your integration)
  5. Run:  python agents/test_bot.py "What's in my Notion workspace?"
"""

import os
import sys
import anyio
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    ResultMessage,
    AssistantMessage,
    SystemMessage,
    TextBlock,
)

# Read-only Notion tools — everything that doesn't mutate
NOTION_READ_TOOLS = [
    "notion-search",
    "notion-fetch",
    "notion-get-comments",
    "notion-get-teams",
    "notion-get-users",
]

# Write tools to block explicitly
NOTION_WRITE_TOOLS = [
    "notion-create-comment",
    "notion-create-database",
    "notion-create-pages",
    "notion-create-view",
    "notion-duplicate-page",
    "notion-move-pages",
    "notion-update-data-source",
    "notion-update-page",
    "notion-update-view",
]

SYSTEM_PROMPT = """\
You are test_bot, a helpful read-only Notion assistant.

You can search and read Notion pages, databases, and comments,
but you cannot create, update, or delete anything.

When answering questions:
- Use notion-search to find pages and databases
- Use notion-fetch to read page content by URL or ID
- Be concise and format results clearly
- If you can't find something, say so rather than guessing
"""


def get_notion_mcp_config() -> dict:
    """Build the Notion MCP server config from environment."""
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        print("ERROR: NOTION_TOKEN environment variable is not set.")
        print("  1. Create an integration at https://www.notion.so/my-integrations")
        print("  2. export NOTION_TOKEN='ntn_your_token_here'")
        sys.exit(1)

    return {
        "command": "npx",
        "args": ["-y", "@notionhq/notion-mcp-server"],
        "env": {
            "OPENAPI_MCP_HEADERS": f'{{"Authorization": "Bearer {token}", "Notion-Version": "2022-06-28"}}',
        },
    }


async def main():
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Search my Notion workspace and tell me what you find."

    print(f"=== test_bot (read-only Notion) ===")
    print(f"Prompt: {prompt}\n")

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={"notion": get_notion_mcp_config()},
            disallowed_tools=NOTION_WRITE_TOOLS,
            max_turns=15,
        ),
    ):
        if isinstance(message, SystemMessage) and message.subtype == "init":
            print(f"  (session: {message.data.get('session_id')})\n")

        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)

        if isinstance(message, ResultMessage):
            print("\n--- Done ---")
            print(f"Stop reason: {message.stop_reason}")


if __name__ == "__main__":
    anyio.run(main)
