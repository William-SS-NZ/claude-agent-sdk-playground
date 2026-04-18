"""Agent Builder — interactive CLI for creating Claude Agent SDK agents."""

import asyncio
import argparse
from pathlib import Path

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)

from agent_builder.utils import Spinner, build_claude_md, format_tool_call
from agent_builder.tools import builder_tools_server


class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *exc): return None

BUILDER_DIR = Path(__file__).parent.resolve()
IDENTITY_DIR = BUILDER_DIR / "identity"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Builder — create agents through conversation")
    parser.add_argument("--verbose", action="store_true", help="Show debug output")
    args = parser.parse_args()
    verbose = args.verbose

    # Build CLAUDE.md from builder's own identity files
    build_claude_md(
        source_dir=str(IDENTITY_DIR),
        output_dir=str(BUILDER_DIR),
        verbose=verbose,
    )

    options = ClaudeAgentOptions(
        setting_sources=["project"],
        cwd=str(BUILDER_DIR),
        mcp_servers={"builder_tools": builder_tools_server},
        allowed_tools=[
            "mcp__builder_tools__scaffold_agent",
            "mcp__builder_tools__write_identity",
            "mcp__builder_tools__write_tools",
            "mcp__builder_tools__test_agent",
            "mcp__builder_tools__registry",
            "mcp__builder_tools__remove_agent",
            "mcp__builder_tools__propose_self_change",
            "mcp__builder_tools__edit_agent",
            "Read", "Write", "Edit", "Glob", "Grep", "Bash",
        ],
        permission_mode="acceptEdits",
        max_turns=50,
        max_budget_usd=5.00,
    )

    print("\n  Agent Builder ready. Describe what agent you'd like to build.")
    print("  Type 'exit' to quit.\n")

    async with ClaudeSDKClient(options=options) as client:
        while True:
            user_input = await asyncio.to_thread(input, "> ")
            if user_input.strip().lower() in ("exit", "quit"):
                break
            if not user_input.strip():
                continue

            await client.query(user_input)
            spinner = Spinner("thinking") if not verbose else None
            if spinner:
                spinner.start()
            try:
                async for message in client.receive_response():
                    if verbose:
                        print(f"[{message.__class__.__name__}] {message}")

                    if isinstance(message, AssistantMessage):
                        if message.error:
                            if spinner: spinner_ctx = spinner.paused()
                            else: spinner_ctx = _NullCtx()
                            with spinner_ctx:
                                print(f"[Error: {message.error}]")
                            continue
                        for block in message.content:
                            ctx = spinner.paused() if spinner else _NullCtx()
                            with ctx:
                                if isinstance(block, TextBlock):
                                    print(block.text)
                                elif isinstance(block, ToolUseBlock):
                                    if verbose:
                                        print(f"  [Tool: {block.name}] Input: {block.input}")
                                    else:
                                        print(format_tool_call(block.name, block.input))
                            if spinner and isinstance(block, ToolUseBlock):
                                spinner.label = f"running {block.name.split('__')[-1]}"
                    elif isinstance(message, ResultMessage):
                        ctx = spinner.paused() if spinner else _NullCtx()
                        with ctx:
                            if message.is_error:
                                print(f"[Failed: {message.subtype}]")
                            if verbose:
                                print(f"  [Session: {message.session_id}]")
                                print(f"  [Turns: {message.num_turns}, Duration: {message.duration_ms}ms]")
                                if message.usage:
                                    print(f"  [Tokens: in={message.usage.get('input_tokens', '?')} out={message.usage.get('output_tokens', '?')}]")
                            if message.total_cost_usd:
                                print(f"  [Cost: ${message.total_cost_usd:.4f}]")
                    elif verbose and isinstance(message, SystemMessage):
                        if message.subtype == "init":
                            print(f"  [Init: {message.data}]")
                    if spinner and isinstance(message, (AssistantMessage,)):
                        spinner.label = "thinking"
            finally:
                if spinner:
                    await spinner.stop()


if __name__ == "__main__":
    asyncio.run(main())
