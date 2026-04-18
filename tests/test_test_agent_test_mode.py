"""Ensure test_agent always restores TEST_MODE=False even when failures occur.

test_agent flips TEST_MODE to True so tools return mocks, runs the prompts,
then restores False in a finally block. A crash in the middle (e.g. the
tools.py import blowing up) must not leave TEST_MODE stuck at True — that
would silently poison every subsequent real run of the agent.
"""

from pathlib import Path

import pytest

from agent_builder.tools import test_agent as test_agent_module
from agent_builder.tools.test_agent import test_agent as run_test_agent, _set_test_mode


TOOLS_PY_STUB = '''\
"""Stub tools.py for TEST_MODE restore testing."""
TEST_MODE = False

def _marker():
    return "ok"
'''


@pytest.fixture
def agent_dir_with_tools(tmp_path: Path) -> Path:
    """Create a minimal agent dir: tools.py + identity files."""
    output = tmp_path / "output"
    output.mkdir()
    agent_dir = output / "crashy"
    agent_dir.mkdir()
    (agent_dir / "tools.py").write_text(TOOLS_PY_STUB, encoding="utf-8")
    (agent_dir / "AGENT.md").write_text("# Agent\nStub.", encoding="utf-8")
    (agent_dir / "SOUL.md").write_text("# Soul\nStub.", encoding="utf-8")
    (agent_dir / "MEMORY.md").write_text("# Memory\nStub.", encoding="utf-8")
    return output


def _read_test_mode(agent_dir: Path) -> str:
    """Return 'True' or 'False' — the current value of TEST_MODE in tools.py."""
    content = (agent_dir / "tools.py").read_text(encoding="utf-8")
    if "TEST_MODE = True" in content:
        return "True"
    if "TEST_MODE = False" in content:
        return "False"
    raise AssertionError("tools.py has no TEST_MODE assignment")


@pytest.mark.asyncio
async def test_test_mode_restored_after_import_crash(
    agent_dir_with_tools: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Simulate _load_tools_server raising — TEST_MODE must still be False afterwards."""
    def boom(_path):
        raise ImportError("simulated tools.py import failure")
    monkeypatch.setattr(test_agent_module, "_load_tools_server", boom)

    agent_dir = agent_dir_with_tools / "crashy"
    assert _read_test_mode(agent_dir) == "False", "precondition"

    result = await run_test_agent(
        {"agent_name": "crashy", "test_prompts": ["hi"]},
        output_base=str(agent_dir_with_tools),
    )

    assert result.get("is_error") is True, "crash should surface as error"
    assert _read_test_mode(agent_dir) == "False", (
        "finally block must restore TEST_MODE=False after _load_tools_server crash"
    )


@pytest.mark.asyncio
async def test_test_mode_restored_after_prompt_crash(
    agent_dir_with_tools: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Simulate _run_one_prompt raising — TEST_MODE must still be restored."""
    async def fake_server(*args, **kwargs):
        pass
    monkeypatch.setattr(test_agent_module, "_load_tools_server", lambda p: fake_server)

    async def crashing_prompt(*args, **kwargs):
        raise RuntimeError("simulated SDK subprocess failure")
    monkeypatch.setattr(test_agent_module, "_run_one_prompt", crashing_prompt)

    agent_dir = agent_dir_with_tools / "crashy"
    assert _read_test_mode(agent_dir) == "False"

    # test_agent catches exceptions inside _run_one_prompt only; a raise from
    # our patched version will propagate out of test_agent. The finally
    # block should still restore TEST_MODE before the exception bubbles.
    with pytest.raises(RuntimeError, match="simulated SDK subprocess failure"):
        await run_test_agent(
            {"agent_name": "crashy", "test_prompts": ["hi"]},
            output_base=str(agent_dir_with_tools),
        )

    assert _read_test_mode(agent_dir) == "False", (
        "finally block must restore TEST_MODE=False even when a prompt run raises"
    )


def test_set_test_mode_toggle(agent_dir_with_tools: Path):
    """Direct sanity check on the helper itself."""
    tools_py = agent_dir_with_tools / "crashy" / "tools.py"
    assert _read_test_mode(agent_dir_with_tools / "crashy") == "False"
    _set_test_mode(tools_py, enabled=True)
    assert _read_test_mode(agent_dir_with_tools / "crashy") == "True"
    _set_test_mode(tools_py, enabled=False)
    assert _read_test_mode(agent_dir_with_tools / "crashy") == "False"
