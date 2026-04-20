# v0.10.x Roadmap

> Consolidated from `docs/superpowers/specs/2026-04-20-agent-builder-v0.10-authoring-and-components-design.md`,
> `docs/superpowers/plans/2026-04-20-agent-builder-v0.10-authoring-and-components.md`,
> `CHANGELOG.md` deferrals, and `TODO.md` PR #1 review section.
>
> **Last built:** 2026-04-21 (post-PR #1 merge, HEAD `cb2d8e5`).

---

## v0.10.0 — Authoring Layer + Components (headline release)

Turn the builder from *composer* (picks from hand-authored recipes) into *assembler-with-authoring-powers* (creates, clones, edits recipes as part of every build). Adds a lightweight `components/` recipe type for frequently reused code/markdown snippets.

**Branch:** `feat/v0.10-authoring-and-components` (create when starting).
**Spec:** `docs/superpowers/specs/2026-04-20-agent-builder-v0.10-authoring-and-components-design.md`
**Plan:** `docs/superpowers/plans/2026-04-20-agent-builder-v0.10-authoring-and-components.md`

### Phase A — Component type *(new recipe kind)*
- [ ] A1: Version bump `0.10.0.dev0`, create `feat/v0.10-authoring-and-components`
- [ ] A2: `Component` schema (frontmatter-in-comment-header, `.py` and `.md` shapes)
- [ ] A3: Component loader (shares validation with recipe loader)
- [ ] A4: `list_recipes` surfaces `type="component"`

### Phase B — `attach_component`
- [ ] B1: New tool — materialises a component into agent files (target + slot semantics)
- [ ] B2: `render_agent` honors AGENT.md component injections
- [ ] B3: Register `attach_component` in builder MCP server

### Phase C — Maturity tiers
- [ ] C1: `maturity: in-dev | experimental | stable` added to `Recipe` schema
- [ ] C2: `list_recipes` hides `in-dev`, shows maturity badge
- [ ] C3: `attach_recipe` refuses `in-dev`, warns on `experimental`

### Phase D — `create_recipe` + Auto-Save Heuristic
- [ ] D1: `recipe-audit.log` writer (every library-modifying action)
- [ ] D2: `create_recipe` tool (TDD)
- [ ] D3: Auto-save heuristic (green-flag / red-flag defaults; builder AGENT.md Phase 2 update)
- [ ] D4: Register `create_recipe`

### Phase E — `clone_recipe`
- [ ] E1: `clone_recipe` with auto-slug generator + collision suffix

### Phase F — `edit_recipe` + Self-Heal Integration
- [ ] F1: `edit_recipe` tool (`.bak-<ts>` + session-scoped edit allowlist)
- [ ] F2: Phase-5 `test_agent` self-heal loop — cap 3 attempts per recipe per session

### Phase G — Doctor + Statusbar
- [ ] G1: Doctor validates components + reports `recipe-audit.log` activity counts
- [ ] G2: Statusbar emits one-liner on every recipe write during a build

### Phase H — Release
- [ ] H1: End-to-end smoke (session creates 1 recipe, clones 1, attaches 3, uses 1 component)
- [ ] H2: Update top-level CLAUDE.md
- [ ] H3: PR + merge

---

## Blocking prerequisites

Deferred out of v0.9.0 and flagged in `CHANGELOG.md#090---2026-04-20` + `TODO.md`. Ship before v0.10.0 work begins.

- [ ] **v0.9.1 — `server` mode template.** FastAPI webhook receiver. Own sub-plan exists (§C1 of v0.9 recipes-and-server spec). Template must validate against the same `REQUIRED_PLACEHOLDERS_BY_MODE` doctor check.
- [ ] **v0.9.2 — Skill recipes.** `type: skill` prose injection into `AGENT.md` (Phase G of v0.9 plan). Paired with **AGENT.md slot-migration on first attach** (tracked in `TODO.md`): today's `_render_agent_md` guard skips slot-less AGENT.mds for safety; skill recipes need those slots populated, so the migration step has to land alongside.
- [ ] **v0.9.x — `edit_agent --resync-recipes`.** Compares `RECIPE_PINS` against current recipe versions, offers per-recipe updates. Blocks the authoring layer because clone/edit cycles will churn versions faster than today.

---

## v0.10.x patch candidates (non-blocking polish)

From `TODO.md` PR #1 review + general polish queue. Tickable in any order after v0.10.0.

- [ ] `telegram_send` caches one `Application` per bot token instead of spinning one up per message.
- [ ] `.poll_state.json` persistent dedupe cache for `telegram-poll` (survives restart, not just in-process LRU).
- [ ] `remove_recipe` tool (deferred from v0.10 acceptance criteria; GC for the growing library).
- [ ] `detach_recipe` / `detach_component` (spec §13, deferred).
- [ ] PR-body smoke-test checkboxes discipline (PR #1 left 3 unchecked at merge — tick off retroactively or on next PR).
- [ ] PR size discipline — recipe library, composition retrofit, poll mode, skill recipes each get their own PR going forward (PR #1 was 12 k lines / 70 files, too wide to review thoroughly).

---

## Deferred to v0.11+ (tracked so they don't leak back in)

Per spec §13:

- Component dependency version constraints (`depends_on` stays name-only in v0.10).
- Recipe marketplace / git-URL fetching / npm-style registry (all recipes remain local and bundled).
- Multi-recipe-server name-conflict UX (SDK namespacing via `mcp__<server>__<tool>` covers today).
- Agent-fix-after-edit flow (tied to resync; only surfaces once resync ships).

---

## Acceptance criteria for cutting v0.10.0

Direct from spec §14 — `CHANGELOG.md#0100` unblocked only when every box below flips.

- [ ] Recipe type `components/` supported by loader, `list_recipes`, `attach_component`.
- [ ] Frontmatter-in-comment-header parser handles both `.py` and `.md` component shapes.
- [ ] Four new builder tools registered: `create_recipe`, `clone_recipe`, `edit_recipe`, `attach_component`.
- [ ] Auto-save heuristic implemented + documented in builder AGENT.md (Phase 2).
- [ ] `maturity` frontmatter field enforced in `list_recipes` and `attach_recipe`.
- [ ] `recipe-audit.log` written on every library-modifying action.
- [ ] Statusbar log line for each recipe write during a build.
- [ ] Self-heal of just-created recipe during test, capped at 3 attempts per recipe.
- [ ] Clone slug auto-generator handles common cases + collision suffix.
- [ ] Doctor extended to validate components + report audit log activity count.
- [ ] Full test suite green including `test_create_recipe`, `test_clone_recipe`, `test_edit_recipe`, `test_attach_component`, `test_auto_save_heuristic`, `test_maturity_tiers`, `test_self_heal_capped`.
- [ ] End-to-end smoke: builder session creates one new recipe, clones an existing one, attaches three, uses one component — agent builds, tests pass.

---

## Known risks (spec §15, worth re-reading before starting Phase D)

- **Library pollution** — every build saving half-thought-out recipes. Mitigation: conservative auto-save green-flag definition; `maturity: experimental` default for self-authored; future `remove_recipe`.
- **Self-heal loops** — 3-attempt cap may not be low enough; drop to 2 if pattern emerges.
- **Clone proliferation** — similar-but-not-quite recipes multiply. Documentation nudges toward edit-in-place over clone for small tweaks.
- **Auto-save false positives** — builder saves something it shouldn't. Ship `remove_recipe` alongside if seen.
- **`edit_recipe` scope creep** — builder confusing "I just created this" with "this already existed". Session-scoped allowlist enforced; `user_requested=True` is the only bypass.
