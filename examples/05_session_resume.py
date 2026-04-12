"""
Session resumption example — continue a conversation across queries.

The Agent SDK supports session IDs so you can resume context from a
previous interaction without re-sending the full history.
"""

import anyio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, SystemMessage


async def main():
    print("=== Session Resumption ===\n")

    session_id = None

    # First query — capture the session ID
    print("--- Query 1: Read the project ---")
    async for message in query(
        prompt="Read pyproject.toml and tell me what this project is about.",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Glob"]),
    ):
        if isinstance(message, SystemMessage) and message.subtype == "init":
            session_id = message.data.get("session_id")
            print(f"  (session: {session_id})")
        if isinstance(message, ResultMessage):
            print(message.result)

    if not session_id:
        print("No session ID captured — cannot resume.")
        return

    # Second query — resume the same session (agent remembers context)
    print("\n--- Query 2: Follow-up question ---")
    async for message in query(
        prompt="Based on what you just read, what dependencies does it use?",
        options=ClaudeAgentOptions(resume=session_id),
    ):
        if isinstance(message, ResultMessage):
            print(message.result)


if __name__ == "__main__":
    anyio.run(main)
