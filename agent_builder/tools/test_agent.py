"""test_agent tool — run generated agent in mock mode and verify it works.

Pass criteria per prompt:
- ResultMessage.subtype == "success"
- No permission_denials and no ResultMessage.errors
- At least one mcp__agent_tools__* tool call observed
- If expected_tools supplied, every listed tool name must appear

A detailed, timestamped log is written to output/<agent_name>/test-run.log
so failures can be diagnosed after the fact.
"""

import ast
import importlib.util
import logging
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    tool,
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    UserMessage,
    TextBlock,
    ToolUseBlock,
)
from agent_builder.utils import build_claude_md


TEST_MODE_ENV_VAR = "AGENT_TEST_MODE"


def _load_tools_server(tools_py_path: Path) -> Any:
    """Dynamically import tools.py and return the tools_server object."""
    spec = importlib.util.spec_from_file_location("generated_tools", str(tools_py_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {tools_py_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generated_tools"] = module
    spec.loader.exec_module(module)
    return module.tools_server


def _count_custom_tools_from_source(tools_py_path: Path) -> int:
    """Count custom tools by parsing tools.py source (no SDK coupling).

    Walks the AST looking for a ``create_sdk_mcp_server(...)`` call and
    returns the number of elements in its ``tools=[...]`` keyword argument.
    Failing to find or parse the call returns 0 so the caller falls back
    to the relaxed "no custom tools" path — same fail-soft behaviour as
    the previous attribute-probing implementation.
    """
    logger = logging.getLogger(__name__)
    try:
        source = tools_py_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError) as e:
        logger.warning("could not parse %s for tool count: %s", tools_py_path, e)
        return 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = None
        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr
        if func_name != "create_sdk_mcp_server":
            continue
        for kw in node.keywords:
            if kw.arg == "tools" and isinstance(kw.value, (ast.List, ast.Tuple)):
                return len(kw.value.elts)
        # call found but no literal tools=[...] — treat as unknown/zero
        return 0

    logger.warning("no create_sdk_mcp_server(...) call found in %s", tools_py_path)
    return 0


def _truncate(s: str, limit: int = 240) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= limit else s[: limit - 1] + "..."


def _setup_logger(agent_dir: Path) -> logging.Logger:
    """Per-agent test-run logger. One handler per agent, appends across runs."""
    log_path = agent_dir / "test-run.log"
    logger_name = f"test_agent.{agent_dir.name}"
    logger = logging.getLogger(logger_name)
    already_attached = any(
        isinstance(h, logging.FileHandler) and Path(h.baseFilename).resolve() == log_path.resolve()
        for h in logger.handlers
    )
    if not already_attached:
        logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)
        logger.propagate = False
    return logger


async def _run_one_prompt(
    prompt: str,
    options: ClaudeAgentOptions,
    expected_tools: list[str] | None,
    logger: logging.Logger,
    require_custom_tool_call: bool = True,
) -> dict[str, Any]:
    """Run a single test prompt and collect structured evidence."""
    started = time.monotonic()
    logger.info("=" * 60)
    logger.info("PROMPT: %s", prompt)

    tools_called: list[str] = []
    assistant_snippets: list[str] = []
    subtype = "unknown"
    num_turns = 0
    duration_ms = 0
    permission_denials: list[Any] = []
    result_errors: list[Any] = []
    first_error: str | None = None

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                if message.error and first_error is None:
                    first_error = str(message.error)
                    logger.error("assistant error: %s", first_error)
                for block in message.content:
                    if isinstance(block, TextBlock):
                        snippet = _truncate(block.text)
                        assistant_snippets.append(snippet)
                        logger.info("assistant: %s", snippet)
                    elif isinstance(block, ToolUseBlock):
                        short = block.name.split("__")[-1] if block.name.startswith("mcp__") else block.name
                        tools_called.append(short)
                        logger.info("tool_use: %s args=%s", block.name, _truncate(block.input))
            elif isinstance(message, UserMessage):
                # Tool results come back as UserMessage content in the SDK
                for block in getattr(message, "content", []) or []:
                    is_error = getattr(block, "is_error", False)
                    if is_error:
                        logger.error("tool_result error: %s", _truncate(getattr(block, "content", "")))
            elif isinstance(message, ResultMessage):
                subtype = message.subtype
                num_turns = message.num_turns
                duration_ms = message.duration_ms
                permission_denials = list(message.permission_denials or [])
                result_errors = list(message.errors or [])
                logger.info(
                    "result: subtype=%s turns=%d duration=%dms denials=%d errors=%d",
                    subtype, num_turns, duration_ms, len(permission_denials), len(result_errors),
                )
                if permission_denials:
                    logger.error("permission_denials: %s", permission_denials)
                if result_errors:
                    logger.error("errors: %s", result_errors)
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("prompt raised: %s\n%s", e, tb)
        first_error = str(e)

    # Evaluate pass/fail
    reasons: list[str] = []
    if subtype != "success":
        reasons.append(f"subtype={subtype}")
    if permission_denials:
        reasons.append(f"{len(permission_denials)} permission denial(s)")
    if result_errors:
        reasons.append(f"{len(result_errors)} result error(s)")
    if first_error:
        reasons.append(f"assistant_error={_truncate(first_error, 80)}")

    if require_custom_tool_call:
        mcp_calls = [t for t in tools_called if t not in ("Read", "Write", "Edit", "Bash", "Glob", "Grep")]
        if not mcp_calls:
            reasons.append("no custom-tool calls observed")

    if expected_tools:
        missing = [t for t in expected_tools if t not in tools_called]
        if missing:
            reasons.append(f"expected tools missing: {missing}")

    status = "pass" if not reasons else "fail"
    elapsed_s = time.monotonic() - started
    logger.info("STATUS: %s (tools=%s, elapsed=%.1fs)", status.upper(), tools_called, elapsed_s)

    return {
        "prompt": prompt,
        "status": status,
        "reasons": reasons,
        "tools_called": tools_called,
        "subtype": subtype,
        "num_turns": num_turns,
        "duration_ms": duration_ms,
        "assistant_preview": assistant_snippets[0] if assistant_snippets else "",
    }


async def test_agent(args: dict[str, Any], output_base: str = "output") -> dict[str, Any]:
    agent_name = args["agent_name"]
    mode = args.get("mode", "cli")

    if mode == "poll":
        return await _test_agent_poll(args, output_base)
    if mode != "cli":
        return {
            "content": [{"type": "text", "text": f"Invalid mode '{mode}'. Expected 'cli' or 'poll'."}],
            "is_error": True,
        }

    test_prompts_raw = args["test_prompts"]
    max_turns = args.get("max_turns", 10)
    # test_prompts can be list[str] or list[{prompt, expected_tools}]
    prompts: list[tuple[str, list[str] | None]] = []
    for p in test_prompts_raw:
        if isinstance(p, str):
            prompts.append((p, None))
        elif isinstance(p, dict):
            prompts.append((p["prompt"], p.get("expected_tools")))

    agent_dir = (Path(output_base) / agent_name).resolve()
    tools_py_path = agent_dir / "tools.py"

    if not tools_py_path.exists():
        return {
            "content": [{"type": "text", "text": f"tools.py not found at {tools_py_path}"}],
            "is_error": True,
        }

    logger = _setup_logger(agent_dir)
    logger.info("###### TEST RUN for '%s' — %d prompts, max_turns=%d ######",
                agent_name, len(prompts), max_turns)

    # Build CLAUDE.md from identity files
    try:
        build_claude_md(source_dir=str(agent_dir), output_dir=str(agent_dir))
    except FileNotFoundError as e:
        logger.error("identity build failed: %s", e)
        return {
            "content": [{"type": "text", "text": f"Identity file missing: {e}"}],
            "is_error": True,
        }

    os.environ[TEST_MODE_ENV_VAR] = "1"
    try:
        try:
            tools_server = _load_tools_server(tools_py_path)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("tools.py import failed: %s\n%s", e, tb)
            return {
                "content": [{"type": "text", "text": f"Failed to import tools.py:\n{tb}"}],
                "is_error": True,
            }

        # Detect "no custom tools" agents (e.g. read-only summarisers that use
        # only built-in Read/Glob/Grep). For these, drop the
        # "must call at least one custom tool" pass criterion and broaden
        # allowed_tools so the agent can actually use the built-ins.
        custom_tool_count = _count_custom_tools_from_source(tools_py_path)
        has_custom_tools = custom_tool_count > 0
        if has_custom_tools:
            allowed = ["mcp__agent_tools__*"]
        else:
            # Narrow to read-only built-ins: a smoke test shouldn't hand a
            # no-tools agent Bash/Edit/Write just to prove it can talk.
            allowed = ["Read", "Glob", "Grep"]
            logger.info("agent has no custom tools — relaxed pass criterion + read-only built-ins")

        options = ClaudeAgentOptions(
            setting_sources=["project"],
            cwd=str(agent_dir),
            mcp_servers={"agent_tools": tools_server},
            allowed_tools=allowed,
            max_turns=max_turns,
        )

        results: list[dict[str, Any]] = []
        for prompt, expected in prompts:
            results.append(await _run_one_prompt(
                prompt, options, expected, logger,
                require_custom_tool_call=has_custom_tools,
            ))

    finally:
        os.environ.pop(TEST_MODE_ENV_VAR, None)
        sys.modules.pop("generated_tools", None)

    passed = sum(1 for r in results if r["status"] == "pass")
    total = len(results)
    lines = [f"Test results for '{agent_name}': {passed}/{total} passed (log: {agent_dir / 'test-run.log'})"]
    for r in results:
        icon = "PASS" if r["status"] == "pass" else "FAIL"
        lines.append(f"  [{icon}] {r['prompt']}")
        lines.append(f"         tools={r['tools_called']} turns={r['num_turns']} duration={r['duration_ms']}ms")
        if r["reasons"]:
            lines.append(f"         reasons: {'; '.join(r['reasons'])}")
        if r["assistant_preview"]:
            lines.append(f"         text: {_truncate(r['assistant_preview'], 120)}")

    logger.info("###### SUMMARY: %d/%d passed ######", passed, total)
    all_passed = passed == total
    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "is_error": not all_passed,
    }


# --- Poll-mode test harness ---------------------------------------------------
#
# test_agent(mode="poll", messages=[...]) exercises a poll-mode agent's
# `async for incoming in poll_source:` loop against synthetic input without
# touching Claude. The harness:
#   1. writes _poll_source_test_stub.py into the agent dir — an async generator
#      that yields Incoming records built from the supplied `messages`,
#   2. backs up agent.py to agent.py.bak-testrun, then rewrites its body so
#      the `async with ClaudeSDKClient(...)` block is replaced with a direct
#      iteration that prints each received message and exits cleanly,
#   3. runs `python agent.py` as a subprocess with AGENT_TEST_MODE=1,
#   4. captures stdout / stderr / exit code,
#   5. always restores agent.py and deletes the stub in a `finally` block.


_POLL_STUB_FILENAME = "_poll_source_test_stub.py"
_POLL_AGENT_BAK_FILENAME = "agent.py.bak-testrun"


def _poll_stub_contents(messages: list[dict[str, Any]]) -> str:
    """Build the source for _poll_source_test_stub.py given a message list.

    `messages` is a list of dicts with at minimum (sender_id, chat_id, text);
    media_refs and raw are optional and default empty.
    """
    return (
        "\"\"\"Synthetic poll source — written by test_agent for mode='poll'.\"\"\"\n"
        "from dataclasses import dataclass, field\n"
        "\n"
        "@dataclass\n"
        "class Incoming:\n"
        "    sender_id: int\n"
        "    chat_id: int\n"
        "    text: str\n"
        "    media_refs: list = field(default_factory=list)\n"
        "    raw: dict = field(default_factory=dict)\n"
        "\n"
        f"_MESSAGES = {messages!r}\n"
        "\n"
        "async def test_poll_source():\n"
        "    for m in _MESSAGES:\n"
        "        yield Incoming(**m)\n"
    )


def _rewrite_agent_py_for_poll_test(agent_py: Path) -> None:
    """Rewrite the poll-mode agent.py so the main loop iterates the test stub
    and skips the real ClaudeSDKClient entirely.

    Locates the `async with ClaudeSDKClient(...) as client:` block and replaces
    everything from that line through the end of `main()` with a minimal loop
    that prints each message and then returns. Imports / safety hook / identity
    setup are left alone so import-time failures still surface.
    """
    content = agent_py.read_text(encoding="utf-8")

    # Inject the stub import next to the existing poll_source_import marker.
    content = re.sub(
        r"(# <<poll_source_import>>\n)(.*?)(\n# <</poll_source_import>>)",
        r"\1from _poll_source_test_stub import test_poll_source, Incoming\n\3",
        content,
        count=1,
        flags=re.DOTALL,
    )

    shim = (
        "    # --- test harness override (AGENT_TEST_MODE=1) ---\n"
        "    _count = 0\n"
        "    async for incoming in test_poll_source():\n"
        "        _count += 1\n"
        "        print(f\"test_agent.poll: received message {_count} from sender={incoming.sender_id}\", flush=True)\n"
        "    print(f\"test_agent.poll: processed {_count} messages\", flush=True)\n"
        "    return\n"
    )

    # Drop everything between the `async with ClaudeSDKClient(...)` line and
    # the module-level `if __name__` sentinel.
    pattern = re.compile(
        r"    async with ClaudeSDKClient\(options=options\).*?(?=\nif __name__)",
        re.DOTALL,
    )
    new_content, n = pattern.subn(shim.rstrip() + "\n", content)
    if n != 1:
        raise RuntimeError(
            "test_agent.poll: could not locate ClaudeSDKClient block in agent.py — "
            "template drift?"
        )
    agent_py.write_text(new_content, encoding="utf-8")


async def _test_agent_poll(args: dict[str, Any], output_base: str) -> dict[str, Any]:
    agent_name = args["agent_name"]
    messages = args.get("messages")

    if not messages or not isinstance(messages, list):
        return {
            "content": [{"type": "text", "text": (
                "mode='poll' requires 'messages': a non-empty list of "
                "{sender_id, chat_id, text} dicts."
            )}],
            "is_error": True,
        }

    # Resolve to absolute upfront: subprocess.run(cwd=...) with a relative path
    # is resolved against caller's cwd, and `.resolve()` on a relative Path is
    # likewise caller-cwd-dependent. If an earlier MCP tool call happened to
    # leave the process cwd elsewhere (e.g. a hook, a library misbehaving),
    # relative paths here double up. Making both paths absolute eliminates the
    # class.
    agent_dir = (Path(output_base) / agent_name).resolve()
    tools_py_path = agent_dir / "tools.py"
    agent_py_path = agent_dir / "agent.py"

    if not tools_py_path.exists() or not agent_py_path.exists():
        return {
            "content": [{"type": "text", "text": f"Agent files missing at {agent_dir}"}],
            "is_error": True,
        }

    logger = _setup_logger(agent_dir)
    logger.info("###### POLL TEST RUN for '%s' — %d messages ######",
                agent_name, len(messages))

    # Rebuild CLAUDE.md so the subprocess agent loads its identity.
    try:
        build_claude_md(source_dir=str(agent_dir), output_dir=str(agent_dir))
    except FileNotFoundError as e:
        logger.error("identity build failed: %s", e)
        return {
            "content": [{"type": "text", "text": f"Identity file missing: {e}"}],
            "is_error": True,
        }

    stub_path = agent_dir / _POLL_STUB_FILENAME
    backup_path = agent_dir / _POLL_AGENT_BAK_FILENAME
    original_agent_py = agent_py_path.read_text(encoding="utf-8")
    backup_path.write_text(original_agent_py, encoding="utf-8")

    stub_path.write_text(_poll_stub_contents(messages), encoding="utf-8")

    stdout = ""
    stderr = ""
    rc = -1
    run_error: str | None = None
    try:
        try:
            _rewrite_agent_py_for_poll_test(agent_py_path)
        except RuntimeError as e:
            logger.error("rewrite failed: %s", e)
            return {
                "content": [{"type": "text", "text": str(e)}],
                "is_error": True,
            }

        env = os.environ.copy()
        env[TEST_MODE_ENV_VAR] = "1"

        try:
            completed = subprocess.run(
                [sys.executable, str(agent_py_path)],
                cwd=str(agent_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            rc = completed.returncode
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            run_error = "subprocess timed out after 30s"
            logger.error(run_error)

        logger.info("subprocess rc=%s", rc)
        if stdout:
            logger.info("stdout:\n%s", stdout)
        if stderr:
            logger.info("stderr:\n%s", stderr)

    finally:
        # Restore agent.py and clean up the stub + backup.
        try:
            agent_py_path.write_text(original_agent_py, encoding="utf-8")
        except OSError as e:
            logger.error("failed to restore agent.py: %s", e)
        for p in (stub_path, backup_path):
            try:
                if p.exists():
                    p.unlink()
            except OSError as e:  # pragma: no cover — best-effort cleanup
                logger.warning("failed to remove %s: %s", p, e)

    # Count how many messages the subprocess reported processing — the shim
    # prints "test_agent.poll: processed N messages" at the end.
    processed = 0
    match = re.search(r"test_agent\.poll: processed (\d+) messages", stdout)
    if match:
        processed = int(match.group(1))

    failure = run_error is not None or rc != 0 or processed != len(messages)

    lines = [
        f"Poll test for '{agent_name}': mode=poll messages_sent={len(messages)} "
        f"processed={processed} rc={rc}"
    ]
    if run_error:
        lines.append(f"  error: {run_error}")
    if stdout:
        lines.append(f"  stdout: {_truncate(stdout, 240)}")
    if stderr:
        lines.append(f"  stderr: {_truncate(stderr, 240)}")
    lines.append(f"  log: {agent_dir / 'test-run.log'}")

    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "is_error": failure,
    }


# MCP tool registration
test_agent_tool = tool(
    "test_agent",
    "Run a generated agent in mock mode (AGENT_TEST_MODE=1) to verify it works. "
    "mode='cli' (default): accepts test_prompts and runs each through query() "
    "with success/denial/error/tool-call pass criteria. "
    "mode='poll': accepts `messages` (list of {sender_id, chat_id, text} dicts) "
    "and runs the agent as a subprocess against a synthetic poll source that "
    "yields them, asserting clean exit + all messages processed. "
    "Writes a timestamped log to output/<agent_name>/test-run.log.",
    {
        "agent_name": str,
        "test_prompts": list,
        "max_turns": int,
        "mode": str,
        "messages": list,
    },
)(test_agent)
