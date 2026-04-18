"""test_agent tool — run generated agent in mock mode and verify it works.

Pass criteria per prompt:
- ResultMessage.subtype == "success"
- No permission_denials and no ResultMessage.errors
- At least one mcp__agent_tools__* tool call observed
- If expected_tools supplied, every listed tool name must appear

A detailed, timestamped log is written to output/<agent_name>/test-run.log
so failures can be diagnosed after the fact.
"""

import importlib.util
import logging
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


def _set_test_mode(tools_py_path: Path, enabled: bool) -> None:
    """Flip TEST_MODE in a tools.py file."""
    content = tools_py_path.read_text(encoding="utf-8")
    if enabled:
        content = content.replace("TEST_MODE = False", "TEST_MODE = True")
    else:
        content = content.replace("TEST_MODE = True", "TEST_MODE = False")
    tools_py_path.write_text(content, encoding="utf-8")


def _load_tools_server(tools_py_path: Path) -> Any:
    """Dynamically import tools.py and return the tools_server object."""
    spec = importlib.util.spec_from_file_location("generated_tools", str(tools_py_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {tools_py_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generated_tools"] = module
    spec.loader.exec_module(module)
    return module.tools_server


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
    test_prompts_raw = args["test_prompts"]
    max_turns = args.get("max_turns", 10)
    # test_prompts can be list[str] or list[{prompt, expected_tools}]
    prompts: list[tuple[str, list[str] | None]] = []
    for p in test_prompts_raw:
        if isinstance(p, str):
            prompts.append((p, None))
        elif isinstance(p, dict):
            prompts.append((p["prompt"], p.get("expected_tools")))

    agent_dir = Path(output_base) / agent_name
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

    _set_test_mode(tools_py_path, enabled=True)
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

        options = ClaudeAgentOptions(
            setting_sources=["project"],
            cwd=str(agent_dir),
            mcp_servers={"agent_tools": tools_server},
            allowed_tools=["mcp__agent_tools__*"],
            max_turns=max_turns,
        )

        results: list[dict[str, Any]] = []
        for prompt, expected in prompts:
            results.append(await _run_one_prompt(prompt, options, expected, logger))

    finally:
        _set_test_mode(tools_py_path, enabled=False)
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


# MCP tool registration
test_agent_tool = tool(
    "test_agent",
    "Run a generated agent in mock mode (TEST_MODE=True) to verify it works. "
    "Accepts test_prompts as either a list of strings or a list of "
    "{prompt: str, expected_tools: [str]} objects. Pass criteria: ResultMessage "
    "success, no permission_denials, no errors, at least one custom-tool call, "
    "and (if supplied) every expected_tools name appears. "
    "Writes a timestamped log to output/<agent_name>/test-run.log.",
    {"agent_name": str, "test_prompts": list, "max_turns": int},
)(test_agent)
