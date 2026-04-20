# Agent Builder v0.10 — Authoring Layer + Components

**Date:** 2026-04-20
**Branch:** `feat/v0.10-authoring-and-components` (to be created after v0.9 ships)
**Status:** Design approved, plan pending
**Depends on:** v0.9 composition model (spec §13)

---

## 1. Goal

Turn the builder from a **composer** (picks from hand-authored recipes) into an **assembler with authoring powers** (creates, clones, and edits recipes as part of every build). Add a lightweight `components/` layer for frequently reused code snippets. Net effect: builder assembles agents mostly, only sometimes authors new parts — and each authored part joins the library for next time.

Motivating use case: user asks builder to build a new agent. Builder scans the library via `list_recipes`, finds 80% match, attaches those recipes, authors the remaining 20% as new recipes or components that become available for the next build.

## 2. Architecture

Builds on v0.9's composition model (manifest + render). Adds four new builder tools and one new recipe type.

```
agent_builder/recipes/
    components/                          # NEW type
        <slug>.py                        # one-file snippets, frontmatter in comment header
        <slug>.md                        # markdown snippets (e.g. helper prompts)

agent_builder/tools/
    create_recipe.py                     # NEW — builder authors a new recipe mid-build
    clone_recipe.py                      # NEW — copies an existing recipe with a new name + mods
    edit_recipe.py                       # NEW — in-place edit (user-requested or self-heal)
    attach_component.py                  # NEW — materializes a component into agent files

agent_builder/
    recipe-audit.log                     # NEW — every recipe/component write logged
```

**Core loop:**

1. `list_recipes()` — builder sees what exists
2. For each need: attach existing recipe, OR clone+modify, OR create new
3. Components handled same way via `list_recipes(type="component")` + `attach_component`
4. Auto-save heuristic (§4) decides: silent create vs prompt-user
5. Every write goes into `recipe-audit.log` + statusbar log line

## 3. Components

Lighter than full recipes. One file per component. Used for frequently reused code/markdown snippets that live inside an agent's own files — not standalone MCP servers.

### 3.1 Format

A single `.py` or `.md` file with frontmatter in a comment header:

`agent_builder/recipes/components/logging-setup.py`:

```python
# ---frontmatter---
# name: logging-setup
# version: 0.1.0
# description: Rotating file logger configured for agent.log
# target: tools.py
# slot: after_imports
# depends_on: []
# maturity: stable
# created_at: 2026-04-20
# git_sha: abc1234
# tags: [logging, observability]
# ---/frontmatter---

import logging
from logging.handlers import RotatingFileHandler

_logger = logging.getLogger("agent")
if not _logger.handlers:
    h = RotatingFileHandler("agent.log", maxBytes=5*1024*1024, backupCount=3)
    _logger.addHandler(h)
```

`agent_builder/recipes/components/timezone-nz.md`:

```markdown
<!-- ---frontmatter---
name: timezone-nz
version: 0.1.0
description: Timezone guidance for New Zealand agents
target: AGENT.md
slot: constraints
maturity: stable
created_at: 2026-04-20
git_sha: abc1234
tags: [timezone, locale, nz]
---/frontmatter--- -->

All dates and times are in Pacific/Auckland (NZST/NZDT). When the user provides relative dates ("Thursday", "tomorrow"), resolve them to absolute dates before acting. When scheduling calendar events, explicitly stamp the timezone.
```

### 3.2 Component targets + slots

Component frontmatter declares **where it lands**:

- `target: tools.py` — component is Python code, appended to agent's bespoke tools.py (not _recipes/, these are always in-agent snippets)
- `target: AGENT.md` + `slot: <name>` — markdown content, routed into the rendered AGENT.md slot
- `target: agent.py` — rarely; component adds imports/helpers at agent.py level (most of this should go in recipes instead)

Slots in `tools.py`:
- `after_imports` — top of file, right after TOOLS_HEADER (most common)
- `after_tools` — bottom, after all tool functions

Slots in `AGENT.md`: same set as v0.9 AGENT.md template (`workflow`, `constraints`, etc.).

Components are **not** standalone MCP servers. They augment existing files.

### 3.3 `attach_component`

New builder tool. Signature:

```
attach_component(agent_name, component_name)
```

What it does:

1. Loads component from `agent_builder/recipes/components/<slug>.{py,md}`.
2. Checks `maturity` — refuses `in-dev`.
3. For `target: tools.py` (Python): reads component body, prepends idempotency header `# component: <name> @ <version>`, appends to agent's `tools.py` at the declared slot (`after_imports` or `after_tools`). Sort deterministically by component name within a slot; respect `depends_on` topological order.
4. For `target: AGENT.md` (markdown): records the component in `.recipe_manifest.json`'s `components` list with its target slot; `render_agent` pulls body and substitutes into the slot on next render.
5. For `target: agent.py`: same idempotent append pattern as tools.py, but inside the recipe_imports_block.
6. Idempotent — if component already in manifest at same version, no-op.
7. Logs to `recipe-audit.log` and statusbar.

Attached components show up in the manifest with their target:

```json
{
  "components": [
    {"name": "logging-setup", "version": "0.1.0", "target": "tools.py:after_imports", "attached_at": "2026-04-20", "git_sha": "abc1234"},
    {"name": "timezone-nz", "version": "0.1.0", "target": "AGENT.md:slot=constraints", "attached_at": "2026-04-20", "git_sha": "abc1234"}
  ]
}
```

## 4. Auto-Save Heuristic for Recipes

When the builder writes a bespoke tool during Phase 2/3 of a build, it evaluates whether the tool is reusable. Decision:

**Green flags → silent auto-save:**
- No hardcoded personal identifiers (names, emails, phone numbers, chat IDs, project IDs)
- Function signature is domain-generic (`send_email(to, subject, body)` yes, `email_taylor(body)` no)
- No references to `AGENT_NAME` or agent-specific constants
- Docstring describes behavior abstractly
- Uses env vars + args only — no reaches into agent-specific state

**Red flags → ask user (once per top-level recipe, not per tool within it):**
- Any hardcoded personal identifier
- References to specific chat_id, project_id, business-name literals
- Function name embeds task specificity (`schedule_hours_for_partner_to_calendar`)
- Heavy coupling to this specific agent's AGENT.md style

**Ambiguous → ask user.**

When asking, builder prompts: "Save `<proposed_name>` as a reusable recipe for future builds? (y/n). Optional: provide a one-line description." Name and description optional overrides.

The ask happens **once per top-level recipe candidate**, not per component of one. If a bespoke tool recipe has 10 @tool functions inside it, user is asked once about saving the whole recipe.

## 5. Maturity Tiers

Frontmatter gains `maturity` (required in v0.10; v0.9 recipes without it default to `experimental` on load):

- **`in-dev`** — work in progress, may be broken. **Completely hidden** by `list_recipes`. **Refused** by `attach_recipe` / `attach_component` with `is_error`. Used by the builder when authoring a recipe it hasn't finished or tested yet.
- **`experimental`** — new or self-authored, unproven. Visible in `list_recipes` with explicit `maturity: experimental` field. `attach_recipe` succeeds but logs a WARN line: "attaching experimental recipe `<name>` — quality not yet verified."
- **`stable`** — tested, reliable. Quiet attach, no warning.

Promotion `experimental → stable` happens via `edit_recipe` with `maturity="stable"` — builder may promote when tests pass repeatedly, or user requests it.

## 6. `create_recipe`

New builder tool. Signature:

```
create_recipe(type, name, description, when_to_use, body, [env_keys], [oauth_scopes], [allowed_tools_patterns], [tags], [maturity])
```

Builder calls this mid-build when:
- It needed a tool/mcp/skill the library doesn't have
- The `auto-save heuristic` (§4) says green (silent) or user said yes (prompted)

What it does:

1. Validates `name` matches slug pattern.
2. Validates type ∈ {tool, mcp, skill, component}.
3. Creates `agent_builder/recipes/<type>/<name>/` (or `.py`/`.md` for component).
4. Writes `RECIPE.md` with full frontmatter. Stamps `created_at` (ISO date) and `git_sha` (7-char short, best-effort — empty string if no git).
5. Writes type-specific siblings (`tool.py`, `mcp.json`, `skill.md`, etc.) from `body`.
6. Validates via recipe loader (parse + sibling checks).
7. On any validation failure, deletes the partial recipe dir and returns `is_error`.
8. On success, appends to `recipe-audit.log`:

   ```
   2026-04-20T14:32:07 CREATE tool/telegram-search@0.1.0 by=builder src=build-session sha=abc1234
   ```

9. Statusbar log line during build: `created recipe: tool/telegram-search → recipes/tools/telegram-search/`.

`overwrite` defaults to `True` (per user decision) — existing recipe of same name is replaced, prior content backed up to `.bak-<timestamp>` next to the target.

## 7. `clone_recipe`

New builder tool. Signature:

```
clone_recipe(source_name, [new_name], modifications, [rationale])
```

Used when: user's requested agent needs something close to but not exactly an existing recipe.

- `source_name` — slug of existing recipe to clone (can be any type)
- `new_name` — optional; if omitted, builder generates via slug heuristic (see below)
- `modifications` — dict of fields to change in frontmatter + optional `body_diff` (unified diff against source body) OR `body_replace` (full replacement)
- `rationale` — optional one-liner recorded in audit log

**Slug generation (when `new_name` omitted):**

Builder picks a descriptive suffix from the modifications. Heuristic: look at `modifications.description` first 3 words, slugify, prepend source name. Fallback: `<source-name>-variant-N` counter. Examples:
- Source `google-calendar`, modified for read-only → `google-calendar-readonly`
- Source `telegram-poll`, modified for multi-channel → `telegram-poll-multichannel`
- Source `x`, no descriptive mod → `x-variant-1`, then `x-variant-2`, etc.

If the heuristic result already exists, append `-2`, `-3`, etc. until unique.

What it does:

1. Load source recipe (fail if not found).
2. Compute new_name if not provided.
3. Deep-copy source directory to `agent_builder/recipes/<type>/<new_name>/`.
4. Apply `modifications` to frontmatter (merge; `None` values delete a field).
5. Apply `body_diff` or `body_replace` to the body file.
6. Bump `version` to `0.1.0` (clones start fresh — not inheriting source version).
7. Stamp new `created_at` / `git_sha`.
8. Set `maturity` based on modification extent: if body_diff changes <10 lines AND no frontmatter risk fields changed, inherit source maturity; else force `experimental`.
9. Validate new recipe via loader. On failure, delete partial dir, return `is_error`.
10. Audit-log: `2026-04-20T14:35:11 CLONE google-calendar@0.1.0 → google-calendar-readonly@0.1.0 by=builder rationale="read-only subset"`.

Pins in already-built agents stay pointed at the original; clones are net-new library additions.

## 8. `edit_recipe`

New builder tool. Signature:

```
edit_recipe(name, modifications, [bump_version=True])
```

**Use cases (restricted):**

1. **User-requested** — user explicitly asks builder to modify a recipe.
2. **Self-heal of newly-created recipe during test** — if `create_recipe` just authored a recipe and the first `test_agent` run fails due to a bug in the recipe code, builder may `edit_recipe` to fix it. This is the ONLY autonomous edit path.

`edit_recipe` must NOT be used to refactor existing stable recipes without user request — that's the job of a human PR.

What it does:

1. Load recipe (fail if not found).
2. Apply `modifications` to frontmatter + body files.
3. Bump `version` by default (patch-level +1, e.g. `0.1.0` → `0.1.1`). Set `bump_version=False` to skip (rare — only used when iterating on a just-created recipe pre-promotion).
4. Update `git_sha` and add field `edited_at` (ISO date).
5. Backup previous version to `.bak-<timestamp>` next to the target file.
6. Validate. On failure, restore from backup.
7. Audit log: `EDIT tool/telegram-search@0.1.0 → 0.1.1 by=builder reason="self-heal:test-failure"`.

Per user's note: proper version sync + updating already-built agents after recipe edit is **deferred** to a later phase (spec §13 future phases). For now, edits affect future attachments only.

## 9. Statusbar / Activity Log

All four new tools (`create_recipe`, `clone_recipe`, `edit_recipe`, `attach_component`) emit a single statusbar line when they run:

```
saved recipe:   tool/telegram-search → recipes/tools/telegram-search/
cloned recipe:  google-calendar → google-calendar-readonly
edited recipe:  telegram-search@0.1.0 → 0.1.1
attached comp:  logging-setup → output/tg-gcal/tools.py (slot: after_imports)
```

Silent when user confirmation wasn't needed; logged always to `recipe-audit.log`.

## 10. `recipe-audit.log`

One-line-per-event append log at `agent_builder/recipe-audit.log`. Format:

```
<ISO-timestamp> <ACTION> <type>/<name>@<version>[ → <new>@<new-version>] by=<builder|user> [reason="..."|rationale="..."] sha=<git-short>
```

Events: `CREATE`, `CLONE`, `EDIT`, `ATTACH_COMPONENT`, `DETACH_COMPONENT` (v0.11). `doctor` reports line count (informational, no OK/FAIL — just a "library activity: N events" line).

## 11. Updated Builder Workflow (Phases)

v0.9 already inserts Phase 2.5. v0.10 extends Phases 2 and 2.5:

**Phase 2 (Tool Design, updated):**
- After designing each tool/mcp need, run the auto-save heuristic (§4).
- If green: include a `create_recipe` call in the Phase 4 tool list.
- If red: ask user once; remember the answer for the rest of this build.
- If cloning is appropriate (found a 90% match recipe), propose `clone_recipe` instead.

**Phase 2.5 (Recipe Attachment, updated):**
- Call `list_recipes()` as before.
- For each matching recipe: attach as-is, OR suggest clone with mods if close-but-not-exact.
- For components that match (skill-level prompts, code snippets): call `attach_component` in the Phase 4 sequence.

**Phase 4 (Generation, updated):**
- Order when recipes/components are in play:
  1. `scaffold_agent`
  2. `write_identity`
  3. `write_tools` (bespoke tools + TOOLS_HEADER)
  4. `create_recipe` for any green-auto-saved or user-approved new recipes (new recipes become part of library BEFORE attach)
  5. `clone_recipe` for any close-match clones
  6. `attach_recipe` for all recipes (existing + newly-created + cloned)
  7. `attach_component` for all components
  8. `registry add`

Step order matters: create/clone must precede attach so the new recipes are loadable. Render runs inside attach — after step 6 the agent.py and AGENT.md are fully assembled.

**Phase 5 (Test, updated):**
- If any test fails AND the failure traces to a just-created recipe (via `create_recipe` in this session): builder MAY call `edit_recipe` with `bump_version=False` to iterate on the new recipe. Self-heal path only; capped at 3 attempts per recipe per session. After 3 failures, mark the recipe `maturity: in-dev` and surface the issue to the user for manual fix.

Failures in pre-existing recipes are NOT auto-edited — that requires explicit user instruction.

## 12. Safety + Guard Rails

- `create_recipe` / `clone_recipe` / `edit_recipe` write to `agent_builder/recipes/` — additive, git-tracked, reversible. No hard stdin confirm (unlike `propose_self_change`).
- `overwrite=True` default (per user decision). `.bak-<timestamp>` on every overwrite. `doctor` reports count of `.bak-*` files in recipes/ (informational); `--sweep` cleans them per existing policy.
- Slug collisions: `create_recipe` with existing name + `overwrite=False` → `is_error`. With `overwrite=True` (default) → backup + replace.
- `in-dev` recipes block `attach_recipe` — ensures half-baked self-authored recipes don't land in user agents accidentally.
- `edit_recipe` restricted to (user-request | self-heal-of-just-created). Builder's AGENT.md enforces this via Phase 5 rules.
- `recipe-audit.log` provides full observability — user can always see what the builder did.
- Doctor validates every recipe in the library same as v0.9 (extended to cover components).

## 13. Out of Scope / Deferred to v0.11+

- **Resync / pin-updating** — when a recipe version changes, already-built agents get notified or auto-updated. Full proposal lands as its own spec.
- **Agent-fix-after-edit** — when `edit_recipe` breaks a recipe that existing agents depend on, a repair flow. Tied to resync.
- **Detach** — `detach_recipe` and `detach_component` commands. Simple in the composition model (remove from manifest + rerender) but not needed for v0.10 goal.
- **Recipe marketplace / fetching from git URLs / npm-style registry** — all recipes stay local and bundled.
- **Component dependency version constraints** — `depends_on` in v0.10 is just a name list; no version ranges.
- **Multi-recipe-server agents with name conflicts** — if two recipes both expose `send`, the SDK handles namespacing (`mcp__a__send` vs `mcp__b__send`); no conflict-detection UX in v0.10.

## 14. Acceptance Criteria (for v0.10.0)

- [ ] New recipe type `components/` supported by loader, `list_recipes`, `attach_component`.
- [ ] Frontmatter-in-comment-header parser handles both `.py` and `.md` component shapes.
- [ ] Four new builder tools registered and available: `create_recipe`, `clone_recipe`, `edit_recipe`, `attach_component`.
- [ ] Auto-save heuristic implemented + documented in builder AGENT.md (Phase 2).
- [ ] `maturity` frontmatter field with `in-dev` | `experimental` | `stable` semantics enforced in `list_recipes` and `attach_recipe`.
- [ ] `recipe-audit.log` written on every library-modifying action.
- [ ] Statusbar log line for each recipe write during a build.
- [ ] Self-heal of just-created recipe during test, capped at 3 attempts per recipe.
- [ ] Clone slug auto-generator handles common cases + collision suffix.
- [ ] Doctor extended to validate components + report audit log activity count.
- [ ] Full test suite green including: `test_create_recipe`, `test_clone_recipe`, `test_edit_recipe`, `test_attach_component`, `test_auto_save_heuristic`, `test_maturity_tiers`, `test_self_heal_capped`.
- [ ] End-to-end smoke: builder session creates one new recipe, clones an existing one, attaches three, uses one component — agent builds, tests pass.

## 15. Risks

- **Library pollution** — every build saving half-thought-out recipes = junk drawer. Mitigations: auto-save heuristic's red flags default to asking; `maturity: experimental` on self-authored; user can prune with `--sweep`-style garbage collection (future).
- **Self-heal loops** — `edit_recipe` during Phase 5 test fails, retries, fails again. Cap of 3 per recipe per session is hard but may not be enough; if pattern emerges, drop to 2.
- **Clone proliferation** — similar-but-not-quite recipes multiply without consolidation. No automated fix; documentation nudges user to prefer edit-in-place over clone for small tweaks they own.
- **Auto-save false positives** — builder auto-saves something that shouldn't be saved. Mitigations: conservative green-flag definition; easy to delete a saved recipe via `remove_agent` analogue (`remove_recipe` — ship in v0.10 or v0.11).
- **edit_recipe for self-heal reaching existing recipes** — builder confuses "I just created this" with "this already existed". Mitigation: builder only edits recipes it explicitly created this session, tracked in a session-scoped list; `edit_recipe` returns `is_error` if called on a recipe not in that list unless `user_requested=True`.
