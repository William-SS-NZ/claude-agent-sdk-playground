"""
Hooks example — intercept tool calls to log or modify agent behavior.

Hooks let you run callbacks before/after tool use. Here we log every
file the agent reads or edits to an audit trail.
"""

import anyio
from datetime import datetime
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher, ResultMessage


async def log_tool_use(input_data, tool_use_id, context):
    """Log tool usage to stdout (swap with file logging in production)."""
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})

    file_path = tool_input.get("file_path") or tool_input.get("pattern") or ""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"  [{timestamp}] {tool_name}: {file_path}")
    return {}


async def main():
    print("=== Agent with Hooks ===\n")
    print("Tool activity log:")

    async for message in query(
        prompt="Find all Python files in this project and summarize what each one does.",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep"],
            hooks={
                "PostToolUse": [
                    HookMatcher(
                        matcher="Read|Glob|Grep",
                        hooks=[log_tool_use],
                    )
                ]
            },
        ),
    ):
        if isinstance(message, ResultMessage):
            print("\n--- Agent Result ---")
            print(message.result)


if __name__ == "__main__":
    anyio.run(main)
