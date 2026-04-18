"""AST-based regression tests for the CLI dispatch wiring in the scaffolded agent.

These tests verify the *structure* of the rendered agent.py, not just the presence
of string literals. They ensure that when cli_mode=True:
  - argparse gains --prompt and --spec args
  - ClaudeSDKClient is used as an async context manager in a dispatch block
  - inside the dispatch block the code calls client.query() then _drain_responses()
    in that order
  - the dispatch block returns before the chat loop is reached
And that when cli_mode=False, none of the dispatch wiring leaks through.

No subprocess is spawned and the SDK is never called — everything happens via
ast.parse on the rendered source.
"""

import ast
from pathlib import Path

import pytest

from agent_builder.tools.scaffold import scaffold_agent


def _render(tmp_path: Path, name: str, cli_mode: bool) -> str:
    """Helper — scaffold an agent and return its rendered agent.py source."""
    # scaffold_agent is async; use pytest-asyncio's event loop via a wrapper.
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        scaffold_agent(
            {"agent_name": name, "description": "ast-wiring test", "cli_mode": cli_mode},
            output_base=str(tmp_path),
        )
    )
    return (tmp_path / name / "agent.py").read_text(encoding="utf-8")


def _find_main_func(tree: ast.Module) -> ast.AsyncFunctionDef:
    """Locate the async main() function in the rendered module."""
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "main":
            return node
    raise AssertionError("main() function not found in rendered agent.py")


def _add_argument_calls(tree: ast.AST) -> list[ast.Call]:
    """Return every parser.add_argument(...) Call node in the tree."""
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_argument":
                calls.append(node)
    return calls


def _async_with_claude_client_nodes(tree: ast.AST) -> list[ast.AsyncWith]:
    """Return every `async with ClaudeSDKClient(...)` node under the given tree."""
    found: list[ast.AsyncWith] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncWith):
            continue
        for item in node.items:
            call = item.context_expr
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "ClaudeSDKClient"
            ):
                found.append(node)
                break
    return found


def _call_name(node: ast.Call) -> str | None:
    """Return 'obj.attr' for `obj.attr(...)`, or 'name' for `name(...)`, else None."""
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    if isinstance(func, ast.Name):
        return func.id
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_argparse_has_prompt_and_spec_arguments(tmp_path: Path):
    """With cli_mode=True, parser.add_argument is called for both --prompt and --spec."""
    await scaffold_agent(
        {"agent_name": "cliwire-args", "description": "x", "cli_mode": True},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "cliwire-args" / "agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    add_calls = _add_argument_calls(tree)
    # Flatten every string-literal positional arg across every add_argument call.
    literal_args_per_call: list[set[str]] = []
    for c in add_calls:
        literals = {
            a.value for a in c.args if isinstance(a, ast.Constant) and isinstance(a.value, str)
        }
        literal_args_per_call.append(literals)

    assert any(
        {"-p", "--prompt"}.issubset(lits) for lits in literal_args_per_call
    ), "no add_argument call declared both -p and --prompt"
    assert any(
        {"-s", "--spec"}.issubset(lits) for lits in literal_args_per_call
    ), "no add_argument call declared both -s and --spec"


@pytest.mark.asyncio
async def test_two_distinct_async_with_claude_client_in_cli_mode(tmp_path: Path):
    """With cli_mode=True there are exactly two `async with ClaudeSDKClient(...)` nodes:
    one for the CLI dispatch block and one for the interactive chat loop."""
    await scaffold_agent(
        {"agent_name": "cliwire-two", "description": "x", "cli_mode": True},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "cliwire-two" / "agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    main_fn = _find_main_func(tree)
    clients = _async_with_claude_client_nodes(main_fn)
    # They should be distinct node objects (not a single node referenced twice).
    assert len(clients) == 2, (
        f"expected exactly 2 `async with ClaudeSDKClient` nodes in main(), got {len(clients)}"
    )
    assert clients[0] is not clients[1]

    # Each should use options=options as a keyword argument.
    for aw in clients:
        call = aw.items[0].context_expr
        assert isinstance(call, ast.Call)
        kwargs = {kw.arg for kw in call.keywords}
        assert "options" in kwargs, "ClaudeSDKClient must be constructed with options=options"


@pytest.mark.asyncio
async def test_dispatch_block_calls_query_then_drain_in_order(tmp_path: Path):
    """The dispatch block's `async with` body contains a `for _p in cli_prompts:` loop
    whose body awaits client.query(_p) then _drain_responses(client, verbose), in that order."""
    await scaffold_agent(
        {"agent_name": "cliwire-order", "description": "x", "cli_mode": True},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "cliwire-order" / "agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    main_fn = _find_main_func(tree)

    # Walk main()'s direct body and find the `if cli_prompts:` statement.
    # The dispatch block is structured as:
    #   cli_prompts = []
    #   if args.prompt: ...
    #   if args.spec: ...
    #   if cli_prompts:
    #       async with ClaudeSDKClient(options=options) as client:
    #           for _p in cli_prompts:
    #               await client.query(_p)
    #               await _drain_responses(client, verbose)
    #       return
    dispatch_if = None
    for stmt in main_fn.body:
        if (
            isinstance(stmt, ast.If)
            and isinstance(stmt.test, ast.Name)
            and stmt.test.id == "cli_prompts"
        ):
            dispatch_if = stmt
            break
    assert dispatch_if is not None, "could not locate `if cli_prompts:` guard in main()"

    # Inside the guard, the first statement should be the dispatch async with.
    async_withs = [s for s in dispatch_if.body if isinstance(s, ast.AsyncWith)]
    assert len(async_withs) == 1, "dispatch guard must contain exactly one async with"
    dispatch_aw = async_withs[0]

    # Its body should contain exactly one `for _p in cli_prompts:` loop.
    for_loops = [s for s in dispatch_aw.body if isinstance(s, ast.For)]
    assert len(for_loops) == 1, "dispatch async with must contain a single for-loop"
    loop = for_loops[0]
    assert isinstance(loop.target, ast.Name) and loop.target.id == "_p"
    assert isinstance(loop.iter, ast.Name) and loop.iter.id == "cli_prompts"

    # Collect the sequence of await-call names in the loop body, in order.
    await_sequence: list[str] = []
    for stmt in loop.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await):
            inner = stmt.value.value
            if isinstance(inner, ast.Call):
                name = _call_name(inner)
                if name is not None:
                    await_sequence.append(name)

    # query must precede _drain_responses.
    assert "client.query" in await_sequence, "dispatch loop body must await client.query(...)"
    assert "_drain_responses" in await_sequence, (
        "dispatch loop body must await _drain_responses(...)"
    )
    assert await_sequence.index("client.query") < await_sequence.index("_drain_responses"), (
        f"client.query must be awaited before _drain_responses, got {await_sequence!r}"
    )


@pytest.mark.asyncio
async def test_dispatch_returns_before_chat_loop(tmp_path: Path):
    """The `if cli_prompts:` guard must contain a `return` statement, and that return
    must textually precede the chat-loop `async with ClaudeSDKClient(...)` node."""
    await scaffold_agent(
        {"agent_name": "cliwire-return", "description": "x", "cli_mode": True},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "cliwire-return" / "agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    main_fn = _find_main_func(tree)

    # Find the `if cli_prompts:` guard and confirm it contains a return.
    dispatch_if = next(
        (
            s
            for s in main_fn.body
            if isinstance(s, ast.If)
            and isinstance(s.test, ast.Name)
            and s.test.id == "cli_prompts"
        ),
        None,
    )
    assert dispatch_if is not None, "missing `if cli_prompts:` guard"
    returns_in_guard = [s for s in dispatch_if.body if isinstance(s, ast.Return)]
    assert returns_in_guard, "`if cli_prompts:` guard must contain a `return`"

    # Locate the two async-with-ClaudeSDKClient nodes in main() and confirm their
    # lineno ordering. Walk only main() (not the whole module).
    clients = _async_with_claude_client_nodes(main_fn)
    assert len(clients) == 2
    dispatch_aw, chat_aw = sorted(clients, key=lambda n: n.lineno)

    # The return must appear between the dispatch async-with and the chat async-with.
    return_line = returns_in_guard[0].lineno
    assert dispatch_aw.lineno < return_line < chat_aw.lineno, (
        f"expected dispatch async-with (line {dispatch_aw.lineno}) < return (line {return_line}) "
        f"< chat async-with (line {chat_aw.lineno})"
    )


@pytest.mark.asyncio
async def test_cli_mode_false_has_no_prompt_or_spec_references(tmp_path: Path):
    """With cli_mode=False the rendered source must not reference cli-only names."""
    await scaffold_agent(
        {"agent_name": "cliwire-off", "description": "x", "cli_mode": False},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "cliwire-off" / "agent.py").read_text(encoding="utf-8")

    # String-level checks — these names simply must not appear anywhere.
    for forbidden in ("args.prompt", "args.spec", "cli_prompts"):
        assert forbidden not in source, (
            f"cli_mode=False rendered source unexpectedly contains {forbidden!r}"
        )

    # AST-level confirmation: exactly one `async with ClaudeSDKClient(...)` (the chat loop).
    tree = ast.parse(source)
    main_fn = _find_main_func(tree)
    clients = _async_with_claude_client_nodes(main_fn)
    assert len(clients) == 1, (
        f"cli_mode=False must render exactly one ClaudeSDKClient async-with, got {len(clients)}"
    )


@pytest.mark.asyncio
async def test_drain_responses_call_counts_by_mode(tmp_path: Path):
    """_drain_responses is called twice when cli_mode=True (chat loop + dispatch) and
    once when cli_mode=False (chat loop only)."""

    def count_drain_calls(source: str) -> int:
        tree = ast.parse(source)
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "_drain_responses":
                    count += 1
        return count

    await scaffold_agent(
        {"agent_name": "cliwire-drain-on", "description": "x", "cli_mode": True},
        output_base=str(tmp_path),
    )
    on_source = (tmp_path / "cliwire-drain-on" / "agent.py").read_text(encoding="utf-8")
    on_count = count_drain_calls(on_source)
    assert on_count >= 2, (
        f"cli_mode=True should call _drain_responses at least twice (chat + dispatch), got {on_count}"
    )

    await scaffold_agent(
        {"agent_name": "cliwire-drain-off", "description": "x", "cli_mode": False},
        output_base=str(tmp_path),
    )
    off_source = (tmp_path / "cliwire-drain-off" / "agent.py").read_text(encoding="utf-8")
    off_count = count_drain_calls(off_source)
    assert off_count >= 1, (
        f"cli_mode=False should still call _drain_responses once (chat loop), got {off_count}"
    )
    # And strictly fewer than the cli_mode=True version.
    assert off_count < on_count, (
        f"cli_mode=False ({off_count}) should have fewer _drain_responses calls than "
        f"cli_mode=True ({on_count})"
    )
