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
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Force UTF-8 on stdout/stderr so the Unicode box-drawing chars, em-dashes,
# and arrows in our output render on Windows terminals that default to cp1252
# (which otherwise raises UnicodeEncodeError mid-print and aborts the run).
# reconfigure() is available on Python 3.7+ TextIOWrapper; wrap in try so
# redirected / buffered streams don't crash import.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

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
from agent_builder.cleanup import sweep_artifacts, delete_swept, format_summary as _format_sweep_summary
from agent_builder.doctor import run_health_check, format_checks as _format_doctor_checks


class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *exc): return None


BUILDER_DIR = Path(__file__).parent.resolve()
IDENTITY_DIR = BUILDER_DIR / "identity"
LOGS_DIR = BUILDER_DIR / "logs"
REPO_ROOT = BUILDER_DIR.parent


def _setup_run_logger() -> tuple[logging.Logger, Path]:
    """Per-invocation logfile at agent_builder/logs/builder-YYYYMMDD-HHMMSS.log.

    Every builder run gets its own timestamped file so forensic analysis of
    a specific session is straightforward. Returns (logger, log_path).
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOGS_DIR / f"builder-{stamp}.log"

    # Use a unique logger name per run so the FileHandler isn't shared across
    # repeated main() invocations in the same process (e.g. tests).
    logger = logging.getLogger(f"agent_builder.run.{stamp}")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)
    logger.propagate = False
    return logger, log_path


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
    allowed_tools = [
        "mcp__builder_tools__scaffold_agent",
        "mcp__builder_tools__write_identity",
        "mcp__builder_tools__write_tools",
        "mcp__builder_tools__test_agent",
        "mcp__builder_tools__registry",
        "mcp__builder_tools__remove_agent",
        "mcp__builder_tools__propose_self_change",
        "mcp__builder_tools__edit_agent",
        "mcp__builder_tools__rollback",
        "mcp__builder_tools__list_recipes",
        "mcp__builder_tools__attach_recipe",
        "Read", "Write", "Edit", "Glob", "Grep", "Bash",
    ]
    # Web access for design research — look up current API docs, verify
    # library/tool names, check best practices before designing tools and
    # writing identity files. Off by default so pasted URLs in discovery
    # don't trigger arbitrary outbound fetches in untrusted environments.
    if os.environ.get("ENABLE_WEB_TOOLS") == "1":
        allowed_tools.extend(["WebFetch", "WebSearch"])
    return ClaudeAgentOptions(
        setting_sources=["project"],
        cwd=str(BUILDER_DIR),
        mcp_servers={"builder_tools": builder_tools_server},
        allowed_tools=allowed_tools,
        permission_mode="acceptEdits",
        max_turns=50,
        max_budget_usd=5.00,
    )


async def _run_one_query(
    client: ClaudeSDKClient,
    user_input: str,
    verbose: bool,
    logger: logging.Logger | None = None,
) -> None:
    if logger:
        logger.info("user_input: %s", user_input)
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
                    if logger:
                        logger.error("assistant error: %s", message.error)
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
                            if logger:
                                logger.info("assistant_text: %s", block.text)
                            print(block.text)
                        elif isinstance(block, ToolUseBlock):
                            if logger:
                                logger.info("tool_use: name=%s input=%s", block.name, block.input)
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
                if logger:
                    logger.info(
                        "result: subtype=%s turns=%s duration_ms=%s cost_usd=%s denials=%d errors=%d",
                        message.subtype, message.num_turns, message.duration_ms,
                        message.total_cost_usd,
                        len(message.permission_denials or []),
                        len(message.errors or []),
                    )
                    if message.permission_denials:
                        logger.warning("permission_denials: %s", message.permission_denials)
                    if message.errors:
                        logger.error("result_errors: %s", message.errors)
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


_MENU_CHOICES: dict[str, tuple[str, str]] = {
    # number → (label, seed prompt sent to the SDK)
    "1": (
        "Build a new agent",
        "I want to build a new agent. Start Phase 1 (Discovery) — ask me about the agent's purpose, propose a name for me to confirm, and walk me through the rest of the workflow.",
    ),
    "2": (
        "Edit an existing agent",
        "I want to edit an existing agent. First call registry with action 'list' to show me what's registered, then ask which one and what should change.",
    ),
    "3": (
        "Test an existing agent",
        "I want to run test_agent against an existing agent. List what's registered first, then ask which one and propose 2–3 test prompts for me to confirm.",
    ),
    "4": (
        "List or describe registered agents",
        "List every agent in the registry (use registry action 'list'), then offer to describe any of them in detail with action 'describe'.",
    ),
    "5": (
        "Remove an agent",
        "I want to remove an agent. List what's registered first, then confirm the exact name with me before calling remove_agent — output/<name>/ is gitignored so the deletion can't be recovered from git.",
    ),
    "6": (
        "Roll back a recent edit",
        "I want to roll back a recent edit. Ask which file (under agent_builder/ or output/<name>/), call rollback action 'list' to show available .bak-<timestamp> backups, then confirm which backup_name to restore before calling rollback action 'restore'.",
    ),
    "7": (
        "Something else — I'll describe it",
        "",  # falls back to user's free-text prompt
    ),
}


def _menu_text() -> str:
    lines = ["", "  What would you like to do?", ""]
    for key, (label, _) in _MENU_CHOICES.items():
        lines.append(f"    {key}. {label}")
    lines.extend([
        "",
        "  Type a number to pick one, type 'menu' to show this again,",
        "  type 'exit' to quit, or just describe what you want in your own words.",
        "",
    ])
    return "\n".join(lines)


def _expand_menu_choice(raw_input: str) -> str | None:
    """If the user typed a menu number, return the seed prompt. Else None."""
    key = raw_input.strip()
    if key not in _MENU_CHOICES:
        return None
    _, seed = _MENU_CHOICES[key]
    return seed or None  # option 7 has empty seed → treat as not-a-menu-pick


async def _interactive_loop(
    client: ClaudeSDKClient,
    verbose: bool,
    logger: logging.Logger | None = None,
) -> None:
    print("\n  Agent Builder ready.")
    print(_menu_text())

    while True:
        try:
            user_input = await asyncio.to_thread(input, "> ")
        except (EOFError, KeyboardInterrupt):
            if logger:
                logger.info("interactive loop interrupted by user")
            print()  # newline so the next prompt isn't glued to the traceback
            break

        stripped = user_input.strip()
        lower = stripped.lower()

        if lower in ("exit", "quit"):
            if logger:
                logger.info("interactive loop exited via 'exit'/'quit'")
            break
        if not stripped:
            continue
        if lower in ("menu", "?", "help"):
            print(_menu_text())
            continue

        seed = _expand_menu_choice(stripped)
        # Menu choices 2, 3, 4, 5, 6 all operate on existing registered agents.
        # If the registry is empty, spending an LLM roundtrip just to be told
        # "there are no agents" is wasted money — short-circuit locally.
        if seed is not None and stripped in ("2", "3", "4", "5", "6"):
            if not _registered_agent_names():
                if logger:
                    logger.info("menu choice %s short-circuited — registry empty", stripped)
                print(
                    "\n  No agents registered yet — that action needs at least one built agent.\n"
                    "  Pick option 1 to build your first agent, or type 'menu' to pick again.\n"
                )
                continue
        prompt_to_send = seed if seed is not None else user_input
        if seed is not None and logger:
            logger.info("menu choice %s expanded to seed prompt", stripped)

        try:
            await _run_one_query(client, prompt_to_send, verbose, logger=logger)
        except KeyboardInterrupt:
            if logger:
                logger.warning("query cancelled mid-flight by user")
            print("\n  [Cancelled — returning to prompt. Type 'exit' to quit.]\n")
        except Exception as e:
            if logger:
                logger.error("query raised: %s\n%s", e, traceback.format_exc())
            raise


async def _batch_run(
    client: ClaudeSDKClient,
    prompts: list[str],
    verbose: bool,
    logger: logging.Logger | None = None,
) -> None:
    failures: list[tuple[int, str, str]] = []
    for i, prompt in enumerate(prompts, 1):
        if logger:
            logger.info("batch prompt %d/%d: %s", i, len(prompts), prompt)
        print(f"\n  ══════════════════════════════════════════════════════════════")
        print(f"   Prompt {i}/{len(prompts)}: {prompt}")
        print(f"  ══════════════════════════════════════════════════════════════")
        try:
            await _run_one_query(client, prompt, verbose, logger=logger)
        except KeyboardInterrupt:
            if logger:
                logger.warning("batch interrupted at prompt %d/%d", i, len(prompts))
            print(f"\n  [Batch interrupted at prompt {i}/{len(prompts)}.]\n")
            raise
        except Exception as e:
            if logger:
                logger.error("batch prompt %d failed: %s\n%s", i, e, traceback.format_exc())
            failures.append((i, prompt, str(e)))
            print(f"\n  [Prompt {i} failed: {e} — continuing with next prompt.]\n")
    if failures:
        print("\n  Batch summary — failures:")
        for idx, prompt, err in failures:
            snippet = prompt if len(prompt) <= 60 else prompt[:57] + "..."
            print(f"    {idx}. {snippet} — {err}")


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


def _cli_sweep(older_than_days: int, yes: bool) -> int:
    """Single filesystem scan, dry-run summary, prompt, then delete the same
    set. No SDK, no cost."""
    summary = sweep_artifacts(REPO_ROOT, older_than_days=older_than_days, dry_run=True)

    nothing_found = (
        not summary["bak_files"]
        and not summary["builder_logs"]
        and summary["screenshots"] is None
    )
    if nothing_found:
        print(f"Nothing to sweep (older than {older_than_days} days).")
        return 0

    print(_format_sweep_summary(summary))

    if not yes:
        if not _confirm("Proceed with delete? [y/N]: "):
            print("Aborted.")
            return 1

    delete_swept(summary)
    print("Swept.")
    return 0


def _cli_doctor() -> int:
    """Run the read-only health audit. No SDK, no cost."""
    checks, exit_code = run_health_check(REPO_ROOT, registry_file=_REGISTRY_PATH)
    print(_format_doctor_checks(checks))
    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")
    if exit_code == 0 and warn_count == 0:
        print("\nHealth check: OK")
    else:
        parts = []
        if fail_count:
            parts.append(f"{fail_count} FAIL")
        if warn_count:
            parts.append(f"{warn_count} WARN")
        print(f"\nHealth check: {', '.join(parts)}")
    return exit_code


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Builder — create agents through conversation",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug output")
    parser.add_argument(
        "-p", "--prompt",
        help="Non-interactive mode: send a single prompt and exit after the response.",
    )
    parser.add_argument(
        "-s", "--spec",
        help="Non-interactive mode: JSON file with {'prompt': '...'} or {'prompts': ['...','...']}.",
    )
    parser.add_argument(
        "-r", "--remove",
        action="append",
        metavar="NAME",
        help="Directly remove an agent (output dir + registry entry). Repeatable. No SDK / no cost. Prompts for confirmation unless --yes.",
    )
    parser.add_argument(
        "-P", "--purge-all",
        action="store_true",
        help="Remove every agent listed in the registry. Prompts for confirmation unless --yes.",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompts for destructive operations (--remove / --purge-all / --sweep).",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Delete stale artifacts (.bak-<ts> files, per-run builder logs, screenshots/). "
             "Prints a dry-run summary and prompts unless --yes. No SDK / no cost.",
    )
    parser.add_argument(
        "--older-than",
        type=int,
        default=7,
        metavar="DAYS",
        help="For --sweep, preserve artifacts newer than this many days (default 7).",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run a read-only health audit (registry, agent dirs, template drift). "
             "Exits 1 if any FAIL. No SDK / no cost.",
    )
    args = parser.parse_args()

    # Direct CLI actions that skip the SDK entirely. All mutually exclusive
    # with each other and with --prompt / --spec.
    direct_flags = sum([
        bool(args.remove),
        bool(args.purge_all),
        bool(args.sweep),
        bool(args.doctor),
    ])
    if direct_flags > 1:
        parser.error("--remove / --purge-all / --sweep / --doctor are mutually exclusive")
    if direct_flags and (args.prompt or args.spec):
        parser.error("--remove / --purge-all / --sweep / --doctor cannot be combined with --prompt / --spec")

    if args.doctor:
        sys.exit(_cli_doctor())
    if args.sweep:
        sys.exit(_cli_sweep(args.older_than, args.yes))
    if args.remove or args.purge_all:
        if args.purge_all:
            sys.exit(await _cli_purge_all(args.yes))
        sys.exit(await _cli_remove(args.remove, args.yes))

    if args.prompt and args.spec:
        parser.error("use --prompt or --spec, not both")

    verbose = args.verbose

    logger, log_path = _setup_run_logger()
    logger.info(
        "##### builder run start — verbose=%s prompt=%s spec=%s #####",
        verbose, bool(args.prompt), bool(args.spec),
    )
    print(f"  Run log: {log_path}")

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

    try:
        async with ClaudeSDKClient(options=_build_options()) as client:
            if prompts is None:
                await _interactive_loop(client, verbose, logger=logger)
            else:
                await _batch_run(client, prompts, verbose, logger=logger)
    except Exception as e:
        logger.error("builder run failed: %s\n%s", e, traceback.format_exc())
        raise
    finally:
        logger.info("##### builder run end #####")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Interrupted. Bye.")
        sys.exit(130)
