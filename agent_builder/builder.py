"""Agent Builder — interactive CLI for creating Claude Agent SDK agents.

Run modes:

    # Interactive chat loop (default)
    python -m agent_builder.builder
    python -m agent_builder.builder --verbose

    # Non-interactive: one prompt, exit when the SDK returns its final result
    python -m agent_builder.builder --prompt "build a markdown summariser called md-summary"

    # Non-interactive: a batch of prompts from a JSON spec
    python -m agent_builder.builder --spec spec.json

Spec file shape:

    {"prompts": ["first prompt", "next prompt", ...]}

Or (single-prompt shorthand):

    {"prompt": "build me a ..."}
"""

import argparse
import asyncio
import json
import sys
import time
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
from agent_builder.tools.remove_agent import remove_agent as _remove_agent_fn
from agent_builder.tools.registry import DEFAULT_REGISTRY as _REGISTRY_PATH


class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *exc): return None


BUILDER_DIR = Path(__file__).parent.resolve()
IDENTITY_DIR = BUILDER_DIR / "identity"


# Map short tool names to human phase labels for the spinner
_PHASE_LABELS = {
    "scaffold_agent":       "Phase 4: scaffolding files",
    "write_identity":       "Phase 4: writing identity files",
    "write_tools":          "Phase 4: writing tool code",
    "registry":             "Phase 4: updating registry",
    "test_agent":           "Phase 5: testing agent (can take 1-3 min)",
    "edit_agent":           "editing existing agent",
    "remove_agent":         "removing agent",
    "propose_self_change":  "self-heal: awaiting your confirmation",
}


def _phase_label_for(tool_name: str) -> str:
    short = tool_name.split("__")[-1]
    return _PHASE_LABELS.get(short, f"running {short}")


def _phase_banner(tool_name: str, seen: set[str]) -> str | None:
    """Return a one-line banner the first time each phase-anchoring tool runs."""
    short = tool_name.split("__")[-1]
    if short not in _PHASE_LABELS or short in seen:
        return None
    seen.add(short)
    return f"\n  ── {_PHASE_LABELS[short]} ──"


def _build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
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
            "mcp__builder_tools__rollback",
            "Read", "Write", "Edit", "Glob", "Grep", "Bash",
        ],
        permission_mode="acceptEdits",
        max_turns=50,
        max_budget_usd=5.00,
    )


async def _run_one_query(client: ClaudeSDKClient, user_input: str, verbose: bool) -> None:
    await client.query(user_input)
    spinner = Spinner("thinking") if not verbose else None
    if spinner:
        spinner.start()
    started = time.monotonic()
    phases_seen: set[str] = set()
    try:
        async for message in client.receive_response():
            if verbose:
                print(f"[{message.__class__.__name__}] {message}")

            if isinstance(message, AssistantMessage):
                if message.error:
                    ctx = spinner.paused() if spinner else _NullCtx()
                    with ctx:
                        print(f"[Error: {message.error}]")
                    continue
                if spinner and message.usage:
                    spinner.add_tokens(
                        input_tokens=int(message.usage.get("input_tokens", 0) or 0),
                        output_tokens=int(message.usage.get("output_tokens", 0) or 0),
                    )
                for block in message.content:
                    ctx = spinner.paused() if spinner else _NullCtx()
                    with ctx:
                        if isinstance(block, TextBlock):
                            print(block.text)
                        elif isinstance(block, ToolUseBlock):
                            banner = _phase_banner(block.name, phases_seen)
                            if banner:
                                print(banner)
                            if verbose:
                                print(f"  [Tool: {block.name}] Input: {block.input}")
                            else:
                                print(format_tool_call(block.name, block.input))
                    if spinner and isinstance(block, ToolUseBlock):
                        spinner.label = _phase_label_for(block.name)
            elif isinstance(message, ResultMessage):
                if spinner and message.total_cost_usd:
                    spinner.set_cost(message.total_cost_usd)
                ctx = spinner.paused() if spinner else _NullCtx()
                with ctx:
                    elapsed = time.monotonic() - started
                    if message.is_error:
                        print(f"[Failed: {message.subtype}] (elapsed {elapsed:.1f}s)")
                    if verbose:
                        print(f"  [Session: {message.session_id}]")
                        print(f"  [Turns: {message.num_turns}, Duration: {message.duration_ms}ms]")
                        if message.usage:
                            print(f"  [Tokens: in={message.usage.get('input_tokens', '?')} out={message.usage.get('output_tokens', '?')}]")
                    if message.total_cost_usd and elapsed > 0:
                        per_min = message.total_cost_usd / (elapsed / 60)
                        print(f"  [Cost: ${message.total_cost_usd:.4f} — elapsed {elapsed:.1f}s — ${per_min:.2f}/min]")
                    else:
                        print(f"  [elapsed {elapsed:.1f}s]")
            elif verbose and isinstance(message, SystemMessage):
                if message.subtype == "init":
                    print(f"  [Init: {message.data}]")
            if spinner and isinstance(message, AssistantMessage):
                spinner.label = "thinking"
    finally:
        if spinner:
            await spinner.stop()


async def _interactive_loop(client: ClaudeSDKClient, verbose: bool) -> None:
    print("\n  Agent Builder ready. Describe what agent you'd like to build.")
    print("  Type 'exit' to quit. Ctrl+C cancels the current response.\n")

    while True:
        try:
            user_input = await asyncio.to_thread(input, "> ")
        except (EOFError, KeyboardInterrupt):
            print()  # newline so the next prompt isn't glued to the traceback
            break
        if user_input.strip().lower() in ("exit", "quit"):
            break
        if not user_input.strip():
            continue

        try:
            await _run_one_query(client, user_input, verbose)
        except KeyboardInterrupt:
            print("\n  [Cancelled — returning to prompt. Type 'exit' to quit.]\n")


async def _batch_run(client: ClaudeSDKClient, prompts: list[str], verbose: bool) -> None:
    for i, prompt in enumerate(prompts, 1):
        print(f"\n  ══════════════════════════════════════════════════════════════")
        print(f"   Prompt {i}/{len(prompts)}: {prompt}")
        print(f"  ══════════════════════════════════════════════════════════════")
        await _run_one_query(client, prompt, verbose)


def _load_spec(spec_path: str) -> list[str]:
    data = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    if isinstance(data, str):
        return [data]
    if "prompts" in data:
        prompts = data["prompts"]
        if not isinstance(prompts, list) or not all(isinstance(p, str) for p in prompts):
            raise ValueError("spec['prompts'] must be a list of strings")
        return prompts
    if "prompt" in data:
        if not isinstance(data["prompt"], str):
            raise ValueError("spec['prompt'] must be a string")
        return [data["prompt"]]
    raise ValueError("spec must contain 'prompt' (str) or 'prompts' (list[str])")


def _registered_agent_names() -> list[str]:
    path = Path(_REGISTRY_PATH)
    if not path.exists():
        return []
    try:
        agents = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [a["name"] for a in agents if "name" in a]


def _confirm(prompt: str) -> bool:
    try:
        answer = input(prompt)
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes")


async def _cli_remove(agent_names: list[str], yes: bool) -> int:
    """Direct remove — no SDK, no model, no cost. Returns exit code."""
    if not agent_names:
        print("No agent names supplied.", file=sys.stderr)
        return 2

    if not yes:
        print("About to delete:")
        for n in agent_names:
            print(f"  - output/{n}/ and its registry entry")
        if not _confirm("Proceed? [y/N]: "):
            print("Aborted.")
            return 1

    failures = 0
    for name in agent_names:
        result = await _remove_agent_fn({"agent_name": name})
        text = result["content"][0]["text"]
        print(text)
        if result.get("is_error"):
            failures += 1
    return 0 if failures == 0 else 1


async def _cli_purge_all(yes: bool) -> int:
    names = _registered_agent_names()
    if not names:
        print("Registry is already empty.")
        return 0
    return await _cli_remove(names, yes)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Builder — create agents through conversation",
    )
    parser.add_argument("--verbose", action="store_true", help="Show debug output")
    parser.add_argument(
        "--prompt",
        help="Non-interactive mode: send a single prompt and exit after the response.",
    )
    parser.add_argument(
        "--spec",
        help="Non-interactive mode: JSON file with {'prompt': '...'} or {'prompts': ['...','...']}.",
    )
    parser.add_argument(
        "--remove",
        action="append",
        metavar="NAME",
        help="Directly remove an agent (output dir + registry entry). Repeatable. No SDK / no cost. Prompts for confirmation unless --yes.",
    )
    parser.add_argument(
        "--purge-all",
        action="store_true",
        help="Remove every agent listed in the registry. Prompts for confirmation unless --yes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts for destructive operations (--remove / --purge-all).",
    )
    args = parser.parse_args()

    # Direct CLI actions that skip the SDK entirely
    if args.remove or args.purge_all:
        if args.prompt or args.spec:
            parser.error("--remove / --purge-all cannot be combined with --prompt / --spec")
        if args.remove and args.purge_all:
            parser.error("use --remove or --purge-all, not both")
        if args.purge_all:
            sys.exit(await _cli_purge_all(args.yes))
        sys.exit(await _cli_remove(args.remove, args.yes))

    if args.prompt and args.spec:
        parser.error("use --prompt or --spec, not both")

    verbose = args.verbose

    build_claude_md(
        source_dir=str(IDENTITY_DIR),
        output_dir=str(BUILDER_DIR),
        verbose=verbose,
    )

    if args.spec:
        prompts = _load_spec(args.spec)
    elif args.prompt:
        prompts = [args.prompt]
    else:
        prompts = None

    async with ClaudeSDKClient(options=_build_options()) as client:
        if prompts is None:
            await _interactive_loop(client, verbose)
        else:
            await _batch_run(client, prompts, verbose)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Interrupted. Bye.")
        sys.exit(130)
