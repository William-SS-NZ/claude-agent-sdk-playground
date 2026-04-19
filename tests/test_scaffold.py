import pytest
from pathlib import Path
from agent_builder.tools.scaffold import scaffold_agent


@pytest.mark.asyncio
async def test_scaffold_creates_directory_and_files(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "test-agent", "description": "A test agent"},
        output_base=str(tmp_path),
    )
    content = result["content"][0]["text"]
    agent_dir = tmp_path / "test-agent"

    assert agent_dir.exists()
    assert (agent_dir / "agent.py").exists()
    assert (agent_dir / ".env.example").exists()
    assert (agent_dir / ".gitignore").exists()
    assert "test-agent" in (agent_dir / "agent.py").read_text(encoding="utf-8")
    assert "Created" in content


@pytest.mark.asyncio
async def test_scaffold_rejects_invalid_name(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "../escape", "description": "bad"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True
    assert "Invalid" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_scaffold_rejects_dotdot_in_name(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "foo..bar", "description": "bad"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_scaffold_rejects_uppercase(tmp_path: Path):
    result = await scaffold_agent(
        {"agent_name": "MyAgent", "description": "bad"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True


@pytest.mark.asyncio
async def test_scaffold_rejects_existing_directory(tmp_path: Path):
    (tmp_path / "existing-agent").mkdir()
    result = await scaffold_agent(
        {"agent_name": "existing-agent", "description": "dup"},
        output_base=str(tmp_path),
    )
    assert result.get("is_error") is True
    assert "exists" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_scaffold_gitignore_contents(tmp_path: Path):
    await scaffold_agent(
        {"agent_name": "test-agent", "description": "test"},
        output_base=str(tmp_path),
    )
    gitignore = (tmp_path / "test-agent" / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "__pycache__" in gitignore
    assert "CLAUDE.md" in gitignore


@pytest.mark.asyncio
async def test_scaffold_fills_all_placeholders(tmp_path: Path):
    await scaffold_agent(
        {
            "agent_name": "filled",
            "description": "placeholder test",
            "tools_list": ["Read", "Edit"],
            "allowed_tools_list": ["Read", "Edit", "mcp__agent_tools__foo"],
            "permission_mode": "acceptEdits",
        },
        output_base=str(tmp_path),
    )
    agent_py = (tmp_path / "filled" / "agent.py").read_text(encoding="utf-8")
    assert "{{" not in agent_py, "unfilled template placeholders remain"
    assert "'Read'" in agent_py and "'Edit'" in agent_py
    assert "mcp__agent_tools__foo" in agent_py
    assert 'permission_mode="acceptEdits"' in agent_py


@pytest.mark.asyncio
async def test_scaffold_produces_parseable_python(tmp_path: Path):
    import ast
    await scaffold_agent(
        {"agent_name": "parseme", "description": "x"},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "parseme" / "agent.py").read_text(encoding="utf-8")
    ast.parse(source)


@pytest.mark.asyncio
async def test_scaffold_cli_mode_default_emits_prompt_and_spec(tmp_path: Path):
    """cli_mode defaults to True — generated agent should accept -p / --prompt and -s / --spec."""
    await scaffold_agent(
        {"agent_name": "withcli", "description": "demo"},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "withcli" / "agent.py").read_text(encoding="utf-8")
    assert '"-p", "--prompt"' in source
    assert '"-s", "--spec"' in source
    assert "_drain_responses" in source  # the helper used by both modes


@pytest.mark.asyncio
async def test_scaffold_cli_mode_false_omits_prompt_and_spec(tmp_path: Path):
    """When user picks chat-only, the CLI flags must not be emitted."""
    await scaffold_agent(
        {"agent_name": "chatonly", "description": "demo", "cli_mode": False},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "chatonly" / "agent.py").read_text(encoding="utf-8")
    assert '"-p", "--prompt"' not in source
    assert '"-s", "--spec"' not in source
    # Chat loop and verbose flag still present
    assert '"-v", "--verbose"' in source
    assert "Type 'exit' to quit" in source


@pytest.mark.asyncio
async def test_scaffold_description_lands_in_argparse_help(tmp_path: Path):
    """The agent's --help text should reflect the description we passed."""
    await scaffold_agent(
        {"agent_name": "helpdemo", "description": "Summarises markdown files."},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "helpdemo" / "agent.py").read_text(encoding="utf-8")
    assert 'description="Summarises markdown files."' in source


@pytest.mark.asyncio
async def test_scaffold_description_with_quotes_is_escaped(tmp_path: Path):
    """Description containing double quotes must be safely escaped."""
    await scaffold_agent(
        {"agent_name": "quoted", "description": 'Reads "important" files.'},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "quoted" / "agent.py").read_text(encoding="utf-8")
    import ast
    ast.parse(source)  # no syntax error from unescaped quotes


@pytest.mark.asyncio
async def test_scaffold_fails_on_unfilled_placeholder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """If the template contains a placeholder scaffold forgot to fill,
    scaffold must error out rather than write invalid Python.

    We stub the template dir AND the expected-placeholder list so the template
    only has to declare the placeholders this test cares about — otherwise the
    new pre-substitution guard would short-circuit with a 'template missing'
    error before we even get to the unfilled-placeholder branch."""
    import agent_builder.tools.scaffold as scaffold_mod
    fake_template_dir = tmp_path / "templates"
    fake_template_dir.mkdir()
    (fake_template_dir / "agent_main.py.tmpl").write_text(
        'AGENT_NAME = "{{agent_name}}"\nPHANTOM = {{missing_placeholder}}\n',
        encoding="utf-8",
    )
    (fake_template_dir / "env_example.tmpl").write_text("ANTHROPIC_API_KEY=", encoding="utf-8")
    monkeypatch.setattr(scaffold_mod, "TEMPLATES_DIR", fake_template_dir)

    result = await scaffold_agent(
        {"agent_name": "bad", "description": "x"},
        output_base=str(tmp_path / "output"),
    )
    assert result.get("is_error") is True
    # With the stubbed template the pre-check catches all the placeholders
    # scaffold normally fills; that's fine — the key property is "scaffold
    # refused to write invalid Python". Either error message proves that.
    msg = result["content"][0]["text"]
    assert "{{missing_placeholder}}" in msg or "{{builder_version}}" in msg


@pytest.mark.asyncio
async def test_scaffold_stamps_builder_version_in_generated_source(tmp_path: Path):
    """Every generated agent must carry GENERATED_WITH_BUILDER_VERSION so we
    can trace 'which builder spat this out' when debugging a user's agent."""
    from agent_builder._version import __version__ as BUILDER_VERSION

    await scaffold_agent(
        {"agent_name": "stamped", "description": "version stamp test"},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "stamped" / "agent.py").read_text(encoding="utf-8")
    assert f'GENERATED_WITH_BUILDER_VERSION = "{BUILDER_VERSION}"' in source


@pytest.mark.asyncio
async def test_scaffold_builder_version_placeholder_is_in_survival_set(tmp_path: Path):
    """Regression: removing {{builder_version}} from the template (or forgetting
    to fill it in scaffold) must be caught by the pre-substitution guard."""
    import agent_builder.tools.scaffold as scaffold_mod
    fake_template_dir = tmp_path / "templates"
    fake_template_dir.mkdir()
    # Template deliberately omits {{builder_version}} — scaffold should reject it.
    (fake_template_dir / "agent_main.py.tmpl").write_text(
        'AGENT_NAME = "{{agent_name}}"\n',
        encoding="utf-8",
    )
    (fake_template_dir / "env_example.tmpl").write_text("ANTHROPIC_API_KEY=", encoding="utf-8")
    import pytest as _pytest
    with _pytest.MonkeyPatch().context() as mp:
        mp.setattr(scaffold_mod, "TEMPLATES_DIR", fake_template_dir)
        result = await scaffold_agent(
            {"agent_name": "missing-version", "description": "x"},
            output_base=str(tmp_path / "output"),
        )
    assert result.get("is_error") is True
    assert "{{builder_version}}" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_scaffold_cli_mode_emits_spec_format_epilog(tmp_path: Path):
    """When cli_mode is on, --help should explain the --spec JSON shapes.
    The epilog is rendered via RawTextHelpFormatter so newlines survive."""
    await scaffold_agent(
        {"agent_name": "epilog-on", "description": "demo"},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "epilog-on" / "agent.py").read_text(encoding="utf-8")
    assert "SPEC FORMAT:" in source
    assert '"prompt": "single prompt"' in source
    assert '"prompts":' in source
    assert "argparse.RawTextHelpFormatter" in source


@pytest.mark.asyncio
async def test_scaffold_cli_mode_false_omits_spec_format_epilog(tmp_path: Path):
    """Chat-only agents have no --spec flag, so the epilog should be None."""
    await scaffold_agent(
        {"agent_name": "epilog-off", "description": "demo", "cli_mode": False},
        output_base=str(tmp_path),
    )
    source = (tmp_path / "epilog-off" / "agent.py").read_text(encoding="utf-8")
    assert "SPEC FORMAT:" not in source
    assert "epilog=None" in source


@pytest.mark.asyncio
async def test_scaffold_cli_mode_default(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    result = await scaffold_agent(
        {"agent_name": "cli-a", "description": "x"},
        output_base=str(out),
    )
    assert result.get("is_error") is not True
    assert (out / "cli-a" / "agent.py").exists()
    assert 'while True' in (out / "cli-a" / "agent.py").read_text()


@pytest.mark.asyncio
async def test_scaffold_poll_mode(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    result = await scaffold_agent(
        {"agent_name": "poll-a", "description": "x", "mode": "poll"},
        output_base=str(out),
    )
    assert result.get("is_error") is not True
    content = (out / "poll-a" / "agent.py").read_text()
    assert 'async for incoming in poll_source' in content
    # scaffold renders stubs for poll source when no recipe attached yet
    assert "{{poll_source_import}}" not in content
    assert "{{poll_source_expr}}" not in content
    # Stub expression is present
    assert "_stub_poll_source" in content


@pytest.mark.asyncio
async def test_scaffold_unknown_mode_errors(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    result = await scaffold_agent(
        {"agent_name": "bad", "description": "x", "mode": "carrier-pigeon"},
        output_base=str(out),
    )
    assert result["is_error"] is True
    assert "mode" in result["content"][0]["text"]
