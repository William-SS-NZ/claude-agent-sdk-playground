"""
Basic Claude Agent SDK example — one-shot query with read-only tools.

This is the simplest way to use the Agent SDK. The `query()` function
sends a prompt, lets the agent work, and streams messages back.
"""

import anyio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage


async def main():
    print("=== Basic Agent Query ===\n")

    async for message in query(
        prompt="What files are in the current directory? Give a brief summary.",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
        ),
    ):
        if isinstance(message, ResultMessage):
            print("\n--- Agent Result ---")
            print(message.result)


if __name__ == "__main__":
    anyio.run(main)
