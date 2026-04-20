"""Ensure test_agent always unsets AGENT_TEST_MODE even when failures occur.

test_agent sets AGENT_TEST_MODE=1 so generated tools return mocks, runs the
prompts, then pops the env var in a finally block. A crash in the middle
(e.g. the tools.py import blowing up) must not leave the env var stuck at
"1" — that would silently poison every subsequent real run of the agent
within this Python process.
"""

import os
from pathlib import Path

import pytest

from agent_builder.tools import test_agent as test_agent_module
from agent_builder.tools.test_agent import test_agent as run_test_agent, TEST_MODE_ENV_VAR


TOOLS_PY_STUB = '''\
"""Stub tools.py for AGENT_TEST_MODE restore testing."""
import os


def _test_mode() -> bool:
    return os.environ.get("AGENT_TEST_MODE") == "1"


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


@pytest.fixture(autouse=True)
def _ensure_env_unset():
    """Guard against cross-test leakage of the env var."""
    os.environ.pop(TEST_MODE_ENV_VAR, None)
    yield
    os.environ.pop(TEST_MODE_ENV_VAR, None)


@pytest.mark.asyncio
async def test_env_var_restored_after_import_crash(
    agent_dir_with_tools: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Simulate _load_tools_server raising — AGENT_TEST_MODE must be unset afterwards."""
    def boom(_path):
        raise ImportError("simulated tools.py import failure")
    monkeypatch.setattr(test_agent_module, "_load_tools_server", boom)

    assert TEST_MODE_ENV_VAR not in os.environ, "precondition"

    result = await run_test_agent(
        {"agent_name": "crashy", "test_prompts": ["hi"]},
        output_base=str(agent_dir_with_tools),
    )

    assert result.get("is_error") is True, "crash should surface as error"
    assert TEST_MODE_ENV_VAR not in os.environ, (
        "finally block must unset AGENT_TEST_MODE after _load_tools_server crash"
    )


@pytest.mark.asyncio
async def test_env_var_restored_after_prompt_crash(
    agent_dir_with_tools: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Simulate _run_one_prompt raising — AGENT_TEST_MODE must still be unset."""
    async def fake_server(*args, **kwargs):
        pass
    monkeypatch.setattr(test_agent_module, "_load_tools_server", lambda p: fake_server)

    async def crashing_prompt(*args, **kwargs):
        raise RuntimeError("simulated SDK subprocess failure")
    monkeypatch.setattr(test_agent_module, "_run_one_prompt", crashing_prompt)

    assert TEST_MODE_ENV_VAR not in os.environ

    # test_agent catches exceptions inside _run_one_prompt only; a raise from
    # our patched version will propagate out of test_agent. The finally
    # block should still unset the env var before the exception bubbles.
    with pytest.raises(RuntimeError, match="simulated SDK subprocess failure"):
        await run_test_agent(
            {"agent_name": "crashy", "test_prompts": ["hi"]},
            output_base=str(agent_dir_with_tools),
        )

    assert TEST_MODE_ENV_VAR not in os.environ, (
        "finally block must unset AGENT_TEST_MODE even when a prompt run raises"
    )
