# Agent Builder v0.9 — Recipes, OAuth, and Server Mode

**Date:** 2026-04-20
**Branch:** `feat/v0.9-recipes-and-server-mode`
**Status:** Design approved, awaiting implementation plan
**Supersedes:** n/a (extends `2026-04-13-agent-builder-design.md`)

---

## 1. Goal

Extend Agent Builder so it can:

1. Scaffold agents with external MCP servers (stdio/HTTP), not just the per-agent in-process tools server.
2. Reuse curated integration components across agents via a **recipes** directory (MCPs, tools, skills).
3. Generate agents that run in three modes — CLI (existing), long-poll worker (new), FastAPI webhook server (new).
4. Scaffold OAuth helper scripts into agents whose attached recipes need them.
5. Let the builder agent discover available recipes at build time so it proposes reuse before hand-rolling new tools — mirroring how Claude Code skills advertise themselves.

The motivating use case is a Telegram-driven screenshot-to-calendar bot for a partner who sends work-hour screenshots; the target experience is "tell the builder I want a Telegram agent that posts to Google Calendar" and it reuses a `telegram-poll` tool recipe and a `google-calendar` MCP recipe rather than hand-writing each.

## 2. Architecture

```
agent_builder/
  recipes/                         # NEW
    mcps/
      <recipe-slug>/
        RECIPE.md                  # frontmatter metadata + prose
        mcp.json                   # MCP server definition
        setup_auth.py.tmpl         # OAuth bootstrap template (optional)
    tools/
      <recipe-slug>/
        RECIPE.md
        tool.py                    # full @tool-decorated code
    skills/
      <recipe-slug>/
        RECIPE.md
        skill.md                   # markdown appended to target agent's AGENT.md

  templates/
    agent_main.py.tmpl             # existing — CLI + optional -p/-s
    agent_poll.py.tmpl             # NEW — long-poll worker loop
    agent_server.py.tmpl           # NEW — FastAPI webhook receiver

  tools/
    attach_recipe.py               # NEW — materializes a recipe into an agent dir
    list_recipes.py                # NEW — returns compact index of available recipes
    scaffold.py                    # MODIFIED — mode + external_mcps params
```

**Call sequence during a build:**

1. Phase 1 — Discovery (unchanged)
2. Phase 2 — Tool Design. Builder calls `list_recipes()` and proposes attaching relevant ones before designing bespoke tools.
3. Phase 2.5 — Recipe Attachment (new). For each confirmed recipe, `attach_recipe` is called.
4. Phase 3 — Identity (unchanged)
5. Phase 4 — Generation. `scaffold_agent` now takes `mode` and `external_mcps`. `write_tools` still runs — recipe-attached tool code is appended to the hand-rolled `tools_code`, not instead of it.
6. Phases 5 (Test) and 6 (Handoff) unchanged in shape but test harness must understand polling/server modes (§9).

## 3. Recipe Format

### 3.1 Frontmatter schema

Every `RECIPE.md` starts with frontmatter. Parsed by `list_recipes` and `attach_recipe`. Drift between frontmatter and siblings (`mcp.json`, `tool.py`) is validated at load time — bad recipes return `is_error` from `list_recipes` rather than being silently skipped.

```yaml
---
name: google-calendar                    # slug, matches dir name, ^[a-z0-9][a-z0-9-]*$
type: mcp                                # mcp | tool | skill
version: 0.1.0                           # semver, stamped into attached agents for resync detection
description: Read/write Google Calendar events via the official MCP server.
when_to_use: >
  User wants the agent to create, update, or read calendar events.
  Handles OAuth2 automatically via setup_auth.py.
env_keys:                                # required .env entries, appended to .env.example
  - name: GOOGLE_OAUTH_CLIENT_SECRETS
    description: Path to OAuth client JSON downloaded from Google Cloud Console.
    example: ./credentials.json
  - name: GOOGLE_OAUTH_TOKEN_PATH
    description: Where setup_auth.py writes the refresh token.
    example: ./token.json
oauth_scopes:                            # if present, triggers setup_auth.py scaffold
  - https://www.googleapis.com/auth/calendar
allowed_tools_patterns:                  # appended to generated agent's allowed_tools
  - mcp__gcal__*
tags: [calendar, google, oauth]
---

# Google Calendar MCP

<Prose body: what it does, caveats, link to upstream MCP repo, known gotchas.>
```

Tool recipes (`type: tool`) omit `mcp.json`/`oauth_scopes`; they have `tool.py` instead and declare `allowed_tools_patterns: [mcp__agent_tools__<fn_name>]`.

Skill recipes (`type: skill`) have only `RECIPE.md` + `skill.md`. They declare no env keys or tool patterns — pure prose injection.

### 3.2 File expectations by type

| type  | Required files                             | Optional               |
| ----- | ------------------------------------------ | ---------------------- |
| mcp   | `RECIPE.md`, `mcp.json`                    | `setup_auth.py.tmpl`   |
| tool  | `RECIPE.md`, `tool.py`                     |                        |
| skill | `RECIPE.md`, `skill.md`                    |                        |

`mcp.json` shape — matches `ClaudeAgentOptions.mcp_servers` entry exactly so the builder does no transformation:

```json
{
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-google-calendar"],
  "env_passthrough": ["GOOGLE_OAUTH_TOKEN_PATH"]
}
```

`env_passthrough` is a builder-specific extension — it's stripped before handing to the SDK, but tells `attach_recipe` which env vars to forward from the agent's `.env` into the MCP subprocess's environment at runtime via a small wrapper in `agent.py`.

## 4. Three Templates

All three templates share the same identity bootstrap (`build_claude_md`), the same `safety_hook`, the same `Spinner`, the same `_drain_responses`. Differences are only in the **driver loop**.

### 4.1 Shared template changes (applies to all three)

Every template gets two new placeholders:

- `{{external_mcp_block}}` — rendered into `mcp_servers` dict:

  ```python
  mcp_servers={
      "agent_tools": tools_server,
      {{external_mcp_block}}   # e.g.  "gcal": {...},
  }
  ```

- `{{recipe_pins_block}}` — rendered near the top of the file as `RECIPE_PINS = {...}` (§7).

`scaffold.py`'s `REQUIRED_PLACEHOLDERS` set grows to cover both; the existing drift guard (template-has-placeholders AND none-survive-substitution) applies to both new placeholders too.

Shape of the existing CLI template `agent_main.py.tmpl` is otherwise unchanged.

### 4.2 `agent_poll.py.tmpl` (long-poll worker — new)

Replaces the `while True: input(...)` loop with a pluggable "source" that yields messages. The source is declared via a new placeholder `{{poll_source_block}}` written by `attach_recipe` when a poll-capable tool is attached (e.g. `telegram-poll`).

Shape:

```python
async def main():
    # … identity + options identical to CLI template …
    async with ClaudeSDKClient(options=options) as client:
        async for incoming in poll_source():        # {{poll_source_block}} defines this
            logger.info("incoming: %s", incoming.summary)
            await client.query(incoming.prompt_for_agent())
            await _drain_responses(client, verbose)
```

`incoming` is a lightweight dataclass (`Incoming(sender_id, text, media_refs, raw)`) defined inline in the template so generated agents don't import from `agent_builder`. The `telegram-poll` recipe supplies the `poll_source` implementation as part of its `tool.py`.

No CLI chat mode in this template. Only one way in: the poll source. Rationale: ambiguity about "why isn't it responding to my stdin" is worse than forcing a separate CLI agent for local testing.

### 4.3 `agent_server.py.tmpl` (FastAPI webhook — new)

```python
from fastapi import FastAPI, Request, HTTPException
import uvicorn

app = FastAPI()
_client: ClaudeSDKClient | None = None

@app.on_event("startup")
async def _boot():
    global _client
    _client = await ClaudeSDKClient(options=options).__aenter__()

@app.on_event("shutdown")
async def _shutdown():
    if _client:
        await _client.__aexit__(None, None, None)

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    # {{webhook_validator_block}} — HMAC/signature check injected by attached recipe
    prompt = {{webhook_prompt_builder}}      # recipe-supplied function: body -> str
    await _client.query(prompt)
    # Server mode swallows streamed output — logged to file, not returned in HTTP response
    async for _ in _client.receive_response():
        pass
    return {"ok": True}
```

Port/host via env (`PORT`, `HOST`). Default host is `127.0.0.1` (loopback only — public bind requires explicit `HOST=0.0.0.0`), default port `8000`. `uvicorn` invoked in `__main__` block. FastAPI + uvicorn added as optional deps (`[server]` extra).

**Scaffold-time guard:** `scaffold_agent` with `mode="server"` refuses to complete unless at least one webhook-capable recipe is attached (or `--no-webhook-recipe` explicitly passed, which renders safe stub placeholders: validator = deny-all, prompt_builder = reject). This prevents accidentally shipping a public endpoint with no signature verification. The `{{webhook_validator_block}}` and `{{webhook_prompt_builder}}` placeholders are filled by the first webhook-capable recipe attached. None ship in v0.9; first such recipe lands alongside a future WhatsApp or GitHub-events integration.

**Security:**
- Webhook signature validation is mandatory when the attached integration recipe declares `webhook_signature: hmac_sha256`. `attach_recipe` injects the validator code; it cannot be silently skipped.
- Sender whitelist enforced in the webhook prompt builder (recipe-supplied). Rejected requests return 403 without invoking the agent.

## 5. OAuth Scaffolding

MCP recipes with `oauth_scopes` set must ship `setup_auth.py.tmpl`. When `attach_recipe` runs on such a recipe:

1. Renders the template into `output/<agent-name>/setup_auth.py` with recipe-specific scopes, client-secrets path, token path.
2. Appends a one-line banner to the agent's `AGENT.md` under a "First-run setup" section: `Run python setup_auth.py once before starting this agent — grants <provider> access.`
3. Prints a notice in the build handoff: "`<provider>` OAuth required — run `python output/<name>/setup_auth.py` once before first run."

The builder itself never touches the browser / client-secret file / token — it only scaffolds the helper. The user runs it. This keeps the builder OAuth-free and portable, and makes the first-run step explicit in the generated agent's own codebase rather than a hidden builder-side dance.

The helper template uses `google-auth-oauthlib` for Google-family providers. Each provider needs its own `setup_auth.py.tmpl` living inside its recipe dir — no shared OAuth library in the builder.

## 6. Builder Context Injection + Phase 2.5

### 6.1 `list_recipes` tool

Returns compact index for builder's consumption:

```json
[
  {
    "name": "telegram-poll",
    "type": "tool",
    "version": "0.1.0",
    "description": "Long-polls Telegram bot API for incoming messages, yields Incoming records.",
    "when_to_use": "Agent runs in poll mode and should react to Telegram DMs.",
    "tags": ["telegram", "messaging", "poll"]
  },
  …
]
```

Filter args: `type`, `tag`. Output capped at ~2 KB per call to stay cheap on context.

### 6.2 AGENT.md workflow update

New Phase 2.5 inserted after Tool Design:

> ### Phase 2.5: Recipe Attachment
>
> Before calling `scaffold_agent`, call `list_recipes()` with relevant tag filters. For each recipe that matches the design, ask the user:
> "Recipe `<name>` (`<description>`) matches — attach it? (yes/no)"
>
> After scaffold+identity+write_tools, call `attach_recipe` once per approved recipe. `attach_recipe` is idempotent per (agent, recipe) pair — calling it twice is a no-op.

The builder's existing "design tools from scratch" path stays valid — if no recipe matches, nothing changes.

## 7. Version Pinning and Future Resync

`attach_recipe` stamps recipe provenance into the agent:

- Tool recipes: a `# recipe: <name> @ <version>` header preceding the copied code in `tools.py`.
- MCP recipes: the agent's `agent.py` gets a `RECIPE_PINS = {"gcal": "0.1.0", ...}` dict near the top, source of truth for resync. All three templates gain a `{{recipe_pins_block}}` placeholder for this; scaffold renders `RECIPE_PINS = {}` when no recipes attached yet, and `attach_recipe` rewrites the dict via a deterministic re-serialization (not a blind append) so re-runs stay stable under version control.
- Skill recipes: `<!-- recipe: <name> @ <version> -->` HTML comment around the injected section in `AGENT.md`.

A future `edit_agent --resync-recipes` (not in v0.9 scope) will compare `RECIPE_PINS` against current `recipes/*/RECIPE.md` versions and offer per-recipe updates. v0.9 ships the stamping; resync ships later once we see how recipes evolve.

## 8. `.env.example` Merging Rules

- Each recipe's env keys appended under a banner: `# --- from recipe: <name> @ <version> ---`
- `attach_recipe` refuses to add a key already present in `.env.example` from a different recipe; conflicts return `is_error` with both sources cited rather than silently shadowing.
- Re-running `attach_recipe` for the same recipe version is a no-op (detected via banner + version match).

## 9. Testing

### 9.1 Recipe validation tests

- `tests/test_recipes.py` — walks `agent_builder/recipes/`, asserts every recipe parses (frontmatter present, required fields, file siblings match declared type).
- Exercised in CI — a broken recipe fails the suite, not just runtime.

### 9.2 `test_agent` updates

Current `test_agent` flips `TEST_MODE = True` in `tools.py` and runs prompts through `query()`. For the new modes:

- **Poll mode**: `test_agent` must inject a synthetic "fake poll source" that yields N predetermined `Incoming` records and asserts the agent processed each. Added as a new test mode param `mode="poll"`.
- **Server mode**: `test_agent` boots the FastAPI app via `TestClient`, POSTs synthetic webhook payloads, asserts the agent handled each. `mode="server"`.
- **CLI mode**: unchanged.

All three modes continue to use `TEST_MODE = True` to get mock responses from tool functions so no external services are hit during test.

### 9.3 Recipe E2E tests (smoke)

For each shipped recipe, a smoke test that:
1. Scaffolds a throwaway agent with that recipe attached
2. Asserts `attach_recipe` produced the expected file changes (env keys added, tool code appended with correct header, setup_auth.py present iff oauth)
3. Asserts `doctor` reports the generated agent as healthy

## 10. Implementation Phasing (Organic Order)

Each phase ships independently and leaves the builder in a usable state. No phase depends on a future one landing. Phases explicitly deferred until actual need: skill recipes, resync tool, non-Google OAuth providers.

| Phase | Adds                                                                 | Ships When                                                              | User-Visible |
| ----- | -------------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------ |
| A     | `recipes/` dir + `RECIPE.md` schema + `list_recipes` + validation tests | Recipe loading plumbing works; `list_recipes` returns empty index.      | No           |
| B     | `attach_recipe` tool (tool-type only) + `.env.example` merge + version stamping | Can attach a tool recipe end-to-end.                                    | Yes          |
| C     | `telegram-poll` tool recipe + `agent_poll.py.tmpl` + scaffold `mode="poll"` + poll-mode `test_agent` | First Telegram bot buildable end-to-end using recipes.                  | Yes          |
| D     | MCP recipe type in `attach_recipe` + `external_mcp_block` + `recipe_pins_block` placeholders in currently-existing templates (CLI + poll) + `scaffold_agent external_mcps` param. (Server template gets the same placeholders when it lands in Phase F.) | Builder can attach arbitrary external MCPs.                             | Yes          |
| E     | OAuth helper scaffolding (`setup_auth.py.tmpl` handling in mcp recipes) + `google-calendar` MCP recipe (first real MCP recipe) | Screenshot-to-calendar bot buildable end-to-end.                        | Yes          |
| F     | `agent_server.py.tmpl` + scaffold `mode="server"` + server-mode `test_agent` + `[server]` extra dep | Webhook-based agents (WhatsApp/Stripe/etc) become possible.             | Yes          |
| G     | Skill recipe type in `attach_recipe` + first skill recipe (`parse-hours-to-events`) | Shared prose-level knowledge reusable across agents.                    | Yes          |

**Phase A is the floor** — after A ships, every subsequent phase can land in isolation on its own PR-sized change. Each phase ends with a version bump: v0.9.0a, v0.9.0b, ... user-facing `v0.9.0` is cut after E (screenshot-to-calendar works). F and G land as v0.9.1+.

## 11. Out of Scope / Explicitly Deferred

- **Resync tool** (`edit_agent --resync-recipes`) — pins ship in v0.9, resync deferred until we see real upgrade churn.
- **Non-Google OAuth providers** — each will need its own `setup_auth.py.tmpl`; shipping Google first, others on demand.
- **WhatsApp Cloud API / Meta integration** — server template supports it architecturally but no WhatsApp recipe ships in v0.9. User's bot will use Telegram path per Phase C+E.
- **Recipe marketplace / remote fetching** — all recipes are local, git-tracked, shipped with the builder repo. No `attach_recipe --from-url`.
- **Shared library import model** (my original proposal B for Q4) — explicitly rejected; all attached recipes are materialized into the agent dir for portability.
- **Claude Code skill injection into builder's system prompt** — rejected in favor of `list_recipes` tool call at Phase 2.5. Avoids bloating every builder session with all recipe content.

## 12. Risks

- **Template drift across three templates** — every identity/spinner/safety-hook update must land in all three. Mitigation: a `doctor` check that all three templates carry the same canonical header blocks + a shared test asserting structural equivalence of the bootstrap sections.
- **MCP subprocess env leakage** — `env_passthrough` forwards specific keys only; an overly broad passthrough would leak secrets. Mitigation: `attach_recipe` asserts every passthrough key is declared in the recipe's `env_keys`.
- **OAuth helper portability** — `setup_auth.py` runs in the user's shell post-build; if their Python env doesn't have `google-auth-oauthlib`, it crashes with a confusing error. Mitigation: helper's first action is to `pip install` its own deps into a venv, or at minimum print a clear "missing dep" error before attempting the flow.
- **Webhook bind on shared hosts** — server template binds `0.0.0.0` by default; on shared machines this exposes the port to other users. Mitigation: default to `127.0.0.1` and require explicit env override to bind public.

## 13. Acceptance Criteria (for the v0.9.0 milestone — end of Phase E)

- [ ] `recipes/` directory shipped with at least two recipes: `telegram-poll` (tool) and `google-calendar` (mcp, with OAuth helper).
- [ ] `list_recipes` and `attach_recipe` builder tools available; Phase 2.5 documented in builder's `AGENT.md`.
- [ ] `scaffold_agent` accepts `mode: "cli" | "poll" | "server"` and `external_mcps` param.
- [ ] Three templates present, all passing doctor's structural checks.
- [ ] User can, in one `python -m agent_builder.builder` session, describe a Telegram→Google Calendar bot and have a runnable agent land in `output/<name>/` with `setup_auth.py` + attached recipes + correct `.env.example`.
- [ ] Full test suite green (`pytest`) including new recipe validation and poll/server test modes.
- [ ] `doctor` reports no warnings on any of the builder's own files or on a freshly-built recipe-using agent.
