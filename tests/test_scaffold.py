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
async def test_scaffold_fails_on_unfilled_placeholder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """If the template contains a placeholder scaffold forgot to fill,
    scaffold must error out rather than write invalid Python."""
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
    assert "{{missing_placeholder}}" in result["content"][0]["text"]
