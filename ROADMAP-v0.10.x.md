# v0.10.x Roadmap

> **Scope discipline.** The maximalist v0.10 plan lives in `docs/superpowers/plans/2026-04-20-agent-builder-v0.10-authoring-and-components.md` and the matching spec. It's preserved for when library scale justifies it. **This file is the actual ship target** — a deliberately narrower cut based on the 2026-04-21 scrutiny pass.
>
> **Why narrower:** Recipe library is 2 recipes used by 1 agent. The maximalist plan (~6,500 LOC, 4 new tools, maturity tiers, auto-save heuristic, self-heal, audit log) is governance infrastructure for a library at 15+ recipes with multiple authors. Building it now is premature. Everything beyond the core — maturity tiers, auto-save, clone, self-heal, audit log, doctor/statusbar — is **evidence-gated**: ships when the library grows enough to warrant it, not on a calendar date.
>
> **Last built:** 2026-04-21 (post-PR #1 merge, HEAD `cac6f2b`).

---

## v0.9.2 — Skill recipes + AGENT.md slot migration *(next release)*

Smallest meaningful release. Unblocks recipe-driven AGENT.md additions which are currently skipped by the `_render_agent_md` guard shipped in v0.9.0.

- [ ] **Skill recipe type** (`type: skill`) — prose injection into AGENT.md. Phase G of the v0.9 plan. `RECIPE.md` + `skill.md` siblings only — no env keys, no tool patterns.
- [ ] **AGENT.md slot-migration-on-first-attach.** When `attach_recipe` runs against a slot-less AGENT.md, wrap existing body in `<!-- SLOT: builder_agent_additions -->` on a one-shot opt-in path. Pairs with skill recipes — no point in skill injection if the target file has no slot to inject into. Writes `.bak-<ts>` (matches the v0.9.0 data-loss guard contract).
- [ ] **One shipped skill recipe** to prove the shape. Candidate: `parse-hours-to-events` (already referenced in v0.9 spec §G).

**Est.:** ~500 LOC, one focused PR. Branch: `feat/v0.9.2-skill-recipes`.

---

## v0.9.3 — Server mode *(demand-gated)*

Only ship if someone asks for it. Partially specced in v0.9 design §F. Otherwise skip straight to v0.10.0.

- [ ] `templates/agent_server.py.tmpl` — FastAPI webhook receiver.
- [ ] `scaffold_agent(mode="server")` — refuses to scaffold without a webhook-capable recipe (matches poll-mode's recipe-required guard).
- [ ] Doctor validation via `REQUIRED_PLACEHOLDERS_BY_MODE["server"]`.
- [ ] `test_agent(mode="server")` — synthetic webhook POSTs.

**Est.:** ~1,500 LOC. Branch: `feat/v0.9.3-server-mode`.

---

## v0.10.0 — Authoring via tool *extension*, not tool *addition* *(cut-down ship target)*

**Headline change from the maximalist plan:** instead of 4 new builder tools, extend the 3 existing ones with a `target="recipe"` mode. Instead of a new `components/` type with its own loader, support single-file recipes under the existing recipe loader. Drop maturity tiers, auto-save heuristic, self-heal, audit log, statusbar, clone, and doctor extensions — those are v0.10.1+ candidates, evidence-gated.

### Phase A — Extend existing tools with `target="recipe"`
- [ ] **A1**: Version bump `0.10.0.dev0`, branch `feat/v0.10-authoring-minimal`.
- [ ] **A2**: Extend `scaffold_agent` — add `target: "agent" | "recipe"` kwarg. When `"recipe"`, writes `recipes/<type>/<slug>/RECIPE.md` + sibling template files instead of `output/<name>/`. Reuses slug validation, path-traversal guard.
- [ ] **A3**: Extend `edit_agent` — add `target: "agent" | "recipe"` kwarg. When `"recipe"`, resolves paths relative to the recipe dir. Reuses `.bak-<ts>` contract, sub-second collision abort, rollback integration.
- [ ] **A4**: Extend `write_tools` or scrap it for recipe use — recipe `tool.py` body-writing already has the same shape as per-agent `tools.py`. Single code path.

**Why extension beats addition:** zero new backup logic, zero new validation, zero new rollback integration. Same tests apply. Same permission surface. Builder's AGENT.md gains 3 paragraphs, not 4 tool-use descriptions.

### Phase B — Single-file components under existing loader
- [ ] **B1**: Recipe loader accepts single-file shape at `recipes/components/<slug>.{py,md}` with leading YAML frontmatter block (same shape as `RECIPE.md` frontmatter — not the comment-header variant from the maximalist spec). Tool/mcp recipes stay directory-based; components are the only single-file kind.
- [ ] **B2**: `attach_recipe` reads `component` type and materialises into target agent files. `target:` + `slot:` fields in the component's frontmatter drive where it lands. No new `attach_component` tool — one code path.
- [ ] **B3**: `render_agent` honors AGENT.md slot injections from attached components. **Prerequisite:** v0.9.2 slot-migration lands first, otherwise injection targets empty.

### Phase C — Release
- [ ] **C1**: End-to-end smoke — builder session authors one new recipe via `scaffold_agent(target="recipe")`, attaches it to a fresh agent, tests pass.
- [ ] **C2**: Update top-level `CLAUDE.md` with the target-kwarg extension pattern.
- [ ] **C3**: PR + merge.

**Est.:** ~1,500 LOC instead of 6,500. One reviewer can audit in an afternoon.

---

## v0.10.1+ — Evidence-gated additions

Each item below ships **only** when its gating condition is observed. No calendar dates. If the condition never fires, the feature never ships.

| Deferred feature | Gate condition | Maximalist plan phase |
|---|---|---|
| `clone_recipe` tool | User manually copies a recipe directory 3+ times in a month, OR asks for it | E |
| Maturity tiers (`in-dev` / `experimental` / `stable`) | Library reaches ≥ 10 recipes AND someone requests hiding work-in-progress | C |
| Auto-save heuristic | User authors ≥ 5 recipes and reports "the prompts are getting in the way" | D3 |
| `recipe-audit.log` | Auto-save ships (and only then — log exists to make auto-save auditable) | D1 |
| Self-heal-during-test loop | ≥ 3 test failures caused by just-created recipes, AND manual fix is demonstrably painful | F2 |
| Doctor extensions + statusbar | Library reaches ≥ 10 recipes | G |
| `remove_recipe` | First recipe needs deletion | (not in maximalist plan) |
| `detach_recipe` / `detach_component` | First user wants to undo an attach | (deferred per spec §13) |
| `edit_agent --resync-recipes` | Two recipe-version bumps land while at least one agent has the old pin | (v0.9 spec §307) |

**Rule:** each gate is a written-down observation. Add it to this file when spotted. Don't ship because it would be nice — ship because it hurts.

---

## v0.10.x patch backlog (polish, non-blocking)

From `TODO.md` PR #1 review. Order by utility-per-LOC, not blocking order.

- [ ] `telegram_send` caches one `Application` per bot token instead of spinning one up per message.
- [ ] `.poll_state.json` persistent dedupe cache for `telegram-poll` (survives restart, not just in-process LRU).
- [ ] PR-body smoke-test checkboxes discipline (PR #1 left 3 unchecked at merge).
- [ ] PR size discipline going forward — recipe library, composition retrofit, poll mode, skill recipes each get their own PR.

---

## v0.11+ (tracked so they don't leak back in)

Mirrors spec §13. These are deferred *by design*, not by scale.

- Component dependency version constraints (`depends_on` stays name-only until proven insufficient).
- Recipe marketplace / git-URL fetching / npm-style registry (all recipes remain local and bundled).
- Multi-recipe-server name-conflict UX (SDK's `mcp__<server>__<tool>` namespacing covers today).
- Agent-fix-after-edit flow (only surfaces once resync ships — which is itself evidence-gated).

---

## Acceptance criteria for cutting v0.10.0

Narrowed from spec §14. The full maximalist acceptance list remains in the plan file.

- [ ] `scaffold_agent(target="recipe", ...)` creates a valid recipe directory; slug validation + path-traversal guard match agent path.
- [ ] `edit_agent(target="recipe", ...)` edits recipe files in-place; `.bak-<ts>` + sub-second collision abort match agent edit contract.
- [ ] Single-file component loader parses frontmatter YAML block from `recipes/components/<slug>.{py,md}`.
- [ ] `attach_recipe` materialises component into target agent; idempotent per `(agent, component@version)`.
- [ ] `render_agent` honors component-driven AGENT.md slot injections **(requires v0.9.2 slot-migration)**.
- [ ] End-to-end: builder authors 1 new recipe, attaches 1 component, agent builds and tests pass.
- [ ] No regressions in v0.9 test suite (currently 265 tests).

---

## Historical context

The maximalist v0.10 plan was written 2026-04-20 as a single forward-looking design. It was correct architecturally but premature economically — builds authoring infrastructure for a library that has 2 recipes. This narrower cut keeps the **extension-not-addition** principle while deferring the governance/automation machinery until library scale actually demands it.

If the library grows past ~10 recipes and the `target="recipe"` extension path stops being enough, revisit the maximalist plan — most of it will still apply, just to a library that now justifies it.
