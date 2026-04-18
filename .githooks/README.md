# Git Hooks

Repo-tracked git hooks for `claude-agent-sdk-playground`. Using `core.hooksPath`
keeps hooks under version control and shared across the team — no husky, no
symlinks, no Node.

## Activation (one-time, per clone)

```bash
git config core.hooksPath .githooks
```

> Note: This is a **per-clone** setting. Git does not allow a repo to enforce
> hooks automatically — each developer must opt in by running the command
> above in their local clone. Re-running it after cloning fresh is required.

To deactivate:

```bash
git config --unset core.hooksPath
```

## Hooks

### `pre-commit`

Runs `python -m pytest -q` against the whole repo before each commit. Behavior:

- Tests pass: commit proceeds.
- Tests fail: commit is aborted with a non-zero exit and a short message.
- `python` not on PATH **or** `pytest` not installed in the active env:
  prints a warning and exits 0 so devs without the venv active are not
  locked out of committing.

### Bypass (use sparingly)

```bash
git commit --no-verify -m "..."
```
