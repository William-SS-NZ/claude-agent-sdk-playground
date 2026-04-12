"""
Preflight checks — verify your environment is ready before running examples.

Run this first to confirm the SDK is installed, the CLI is available,
and your API key is set.
"""

import sys
import shutil
import os


def check_python_version():
    v = sys.version_info
    ok = v >= (3, 10)
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] Python >= 3.10 (found {v.major}.{v.minor}.{v.micro})")
    return ok


def check_sdk_installed():
    try:
        import claude_agent_sdk  # noqa: F401
        print(f"  [OK] claude-agent-sdk installed")
        return True
    except ImportError:
        print("  [FAIL] claude-agent-sdk not installed")
        print("         Fix: pip install claude-agent-sdk")
        return False


def check_anyio_installed():
    try:
        import anyio  # noqa: F401
        print("  [OK] anyio installed")
        return True
    except ImportError:
        print("  [FAIL] anyio not installed")
        print("         Fix: pip install anyio")
        return False


def check_cli_available():
    path = shutil.which("claude")
    if path:
        print(f"  [OK] claude CLI found at {path}")
        return True
    else:
        print("  [FAIL] claude CLI not found on PATH")
        print("         Fix: npm install -g @anthropic-ai/claude-code")
        return False


def check_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        masked = key[:8] + "..." + key[-4:]
        print(f"  [OK] ANTHROPIC_API_KEY is set ({masked})")
        return True
    else:
        print("  [WARN] ANTHROPIC_API_KEY not set")
        print("         The agent SDK uses the Claude CLI's auth, so this")
        print("         may be fine — but direct API examples will need it.")
        print("         Fix: cp .env.example .env && edit .env")
        return True  # non-fatal


def main():
    print("=== Preflight Checks ===\n")

    results = [
        check_python_version(),
        check_sdk_installed(),
        check_anyio_installed(),
        check_cli_available(),
        check_api_key(),
    ]

    print()
    passed = sum(results)
    total = len(results)

    if all(results):
        print(f"All {total} checks passed. You're ready to go.")
        print("Try: python examples/01_basic_query.py")
    else:
        failed = total - passed
        print(f"{passed}/{total} passed, {failed} failed. Fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
