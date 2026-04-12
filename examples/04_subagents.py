"""
Subagents example — delegate work to specialized child agents.

The main agent can spawn subagents for focused tasks. Each subagent
gets its own tool set and prompt, keeping concerns separated.
"""

import anyio
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    ResultMessage,
)


async def main():
    print("=== Subagent Orchestration ===\n")

    async for message in query(
        prompt=(
            "Use the code-reviewer agent to review the Python files in this project. "
            "Then use the summarizer agent to give a high-level overview of the project."
        ),
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep", "Agent"],
            agents={
                "code-reviewer": AgentDefinition(
                    description="Reviews Python code for quality, security, and best practices.",
                    prompt=(
                        "You are an expert Python code reviewer. "
                        "Analyze code quality, flag potential issues, and suggest improvements. "
                        "Be concise and actionable."
                    ),
                    tools=["Read", "Glob", "Grep"],
                ),
                "summarizer": AgentDefinition(
                    description="Summarizes project structure and purpose.",
                    prompt=(
                        "You are a technical writer. "
                        "Read the project files and produce a brief, clear summary "
                        "of what the project does and how it's organized."
                    ),
                    tools=["Read", "Glob", "Grep"],
                ),
            },
        ),
    ):
        if isinstance(message, ResultMessage):
            print(message.result)


if __name__ == "__main__":
    anyio.run(main)
