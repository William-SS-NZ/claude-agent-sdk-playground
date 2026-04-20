# TODO

Outstanding work for future sessions. Not everything here is a bug — some are polish, some are quality-of-life, some are deferred by design.

## Shipped in [Unreleased] — post-audit fixes

See `audit.md` for the full findings list and `CHANGELOG.md` for the flagged sections.

- [x] ~~Doctor template-drift guard drifted from scaffold~~ — both now import `REQUIRED_PLACEHOLDERS` from `tools/scaffold.py`.
- [x] ~~`write_identity` MCP schema omitted `user_md`~~ — USER.md path reachable via SDK.
- [x] ~~`.bak-<timestamp>` sub-second collisions silently clobbered originals~~ — `edit_agent` and `self_heal` now abort on collision (match `rollback`).
- [x] ~~`self_heal` could rewrite `tools/self_heal.py` and remove the confirmation gate~~ — added to deny list.
- [x] ~~`scaffold._validate_agent_name` used `startswith` (fragile on Windows)~~ — switched to `resolved.relative_to(base)` pattern.
- [x] ~~Dead `test_prompts` preview branch in `format_tool_call`~~ — wired into the mcp fallback.
- [x] ~~`_batch_run` aborted whole batch on one prompt failure~~ — per-prompt failure isolation + end-of-run summary.
- [x] ~~`--doctor` output hid WARN counts~~ — CLI summary now reports `N FAIL, M WARN`.
- [x] ~~`safety_hook` blocked-pattern list was sparse~~ — expanded, and explicitly labelled as defense-in-depth (not a sandbox) in template + README.
- [x] ~~`build_claude_md` rewrote CLAUDE.md even when unchanged~~ — skip-if-identical to avoid mtime thrash.

## Shipped in v0.7.0

- [x] ~~`--sweep` CLI flag~~ — cleans `.bak-<ts>` files, per-run builder logs, repo-root `screenshots/`. `--older-than DAYS` (default 7).
- [x] ~~`--doctor` CLI flag~~ — registry integrity, orphan output dirs, template placeholder drift, missing identity files, unfilled scaffold placeholders.
- [x] ~~`GENERATED_WITH_BUILDER_VERSION` stamp~~ — every generated agent carries the builder version it was scaffolded with.
- [x] ~~Hardcoded `version="1.0.0"` drift~~ — `agent_builder/_version.py` is now the single source of truth.
- [x] ~~Spec-file-format epilog on generated agent `--help`~~.
- [x] ~~AST regression test for cli_mode wiring~~.
- [x] ~~Menu options 2-6 short-circuit when registry empty~~.

## Shipped in v0.9.0

See `CHANGELOG.md#090---2026-04-20` for the full set. The items below are the rollups from the v0.8 backlog that landed as part of the v0.9 release.

- [x] ~~Replace `_set_test_mode` file mutation with an env var (R1)~~ — generated `TOOLS_HEADER` reads `AGENT_TEST_MODE`; `test_agent` sets/unsets the env var and never writes `tools.py`. Kill-mid-run no longer leaves stuck test mode.
- [x] ~~Dedupe Spinner / format_tool_call / build_claude_md across builder + template (R6)~~ — generated agents now `from agent_builder.utils import ...`. Three copies collapsed to one; guard tests in `tests/test_template_imports.py` prevent regression.
- [x] ~~Consolidate path validators (R5)~~ — `agent_builder/paths.py::validate_relative_to_base`. `scaffold`, `remove_agent`, `rollback`, `self_heal` all delegate.
- [x] ~~Gate `WebFetch` / `WebSearch` behind `ENABLE_WEB_TOOLS=1` (R2)~~ — off by default, opt-in via env var.
- [x] ~~Lazy `self_heal` FileHandler (R3)~~ — moved into `propose_self_change`; no handle leak at import time.
- [x] ~~`_cli_sweep` double-scan (R4)~~ — single scan, retained list, second pass deletes.

## High-priority — next release

Audit deferrals still outstanding.

- [ ] **`python -m build` smoke test.** Verify `PolyForm-Noncommercial-1.0.0` passes modern setuptools license-classifier validation without warnings. Blocks any future PyPI publish.
- [ ] **`make setup` / one-shot onboarding script** — new contributor clones, runs one command, gets hooks activated + editable install + test run. Currently three manual steps.
- [ ] **Complexity refactors on `_run_one_query`, `scaffold_agent`, `test_agent`.** Audit items 4.1–4.3. Each splits into 2–3 helpers. Risk: low; diff: chunky.

## From PR #1 review (v0.9 code review pass)

Latent data-loss + polish items surfaced while reviewing the v0.9 PR. Tests pass but these would bite real users on second-use paths.

- [x] ~~**`render_agent` nukes hand-written AGENT.md on re-attach (DATA LOSS).**~~ Fixed: `_render_agent_md` now (a) skips the render entirely when AGENT.md has no SLOT markers — the write_identity shape — and (b) writes a `.bak-<ts>` sibling before any overwrite so the change is reversible via `rollback`. Regression tests in `test_render.py::test_render_preserves_slotless_hand_written_agent_md` + `test_render_backs_up_agent_md_before_overwrite`.
- [ ] **AGENT.md slot-migration on first attach (v0.9.2 / skill-recipe work).** When skill recipes arrive, existing hand-written AGENT.mds need a one-shot migration: wrap their body in a `builder_agent_additions` slot so subsequent renders can coexist with rendered purpose/workflow/constraints slots. Until then, the slot-less skip-guard above keeps content safe at the cost of recipe-driven AGENT.md additions being invisible on old agents.
- [ ] **`attach_recipe` version bump → no-op on already-attached recipe.** Idempotence key is `(agent, recipe@version)`; re-attaching an identical `(name, version)` pair is a no-op, but attaching a *newer* version isn't explicitly documented as the upgrade path. Add `attach_recipe --resync` (v0.9.x) that compares `RECIPE_PINS` against current recipe versions and rewrites the manifest+_recipes copy for any drift. Without this, recipe fixes (e.g. `telegram-poll` 0.1.0 → 0.1.1 dedupe) don't propagate to existing agents.
- [ ] **`telegram_send` spins up a fresh `Application` per message.** Each send opens a bot app instance, initialises, sends, tears down. Fine at low volume; wasteful under chat bursts. Cache one `Application` keyed on bot token and reuse.
- [ ] **Dedup state is per-process memory.** The telegram-poll `_seen_update_ids` list resets on agent restart. Telegram API only redelivers updates within a short window, so this is almost never a problem in practice, but a persistent cache (e.g. `.poll_state.json`) would also cover crash-recovery scenarios.
- [ ] **PR #1 smoke-test checkboxes still open.** The test plan lists three unchecked items: interactive Telegram+Calendar build, `setup_auth.py` OAuth smoke, and generated-agent accepting a Telegram message. The Telegram end-to-end was exercised manually in the 2026-04-20 mc-shift-mgr session — tick those off in the PR body before merge.
- [ ] **PR #1 is 12 k lines / 70 files.** Too large for a single review pass. Future feature branches should split recipe library, composition retrofit, and poll mode into separate PRs so each gets a focused review window.

## Polish / nice-to-have

- [ ] Builder's own `MEMORY.md` never updates itself. Every agent build / edit / remove could be logged back so the builder "remembers" what it's done across sessions. Today it just sits static.
- [ ] Builder has no `USER.md` — user identity / preferences aren't personalised. Could match the generated-agent contract (optional `USER.md` loaded if present).
- [ ] Generated agents' `--help` currently has no link to the generated agent's own README or docs (they don't have one). If future builds include a README, wire it into help output.
- [ ] Self-heal's audit log (`agent_builder/self-heal.log`) has no UI for browsing — only raw tail. A `--show-self-heals [--last N]` CLI flag would expose it.
- [ ] Rollback tool handles one backup at a time. Batch rollback (`rollback all backups from today`) would help recover from a bad multi-file self-heal.
- [ ] No way to diff before applying a self-heal — user sees snippets but not a full unified diff. Could show `difflib.unified_diff` output.
- [ ] Registry has no concept of "agent status" beyond the free-text `status` field. Could add structured states (`draft`, `active`, `archived`, `broken`) with lifecycle transitions.
- [ ] `test_agent` max_turns has to be guessed per agent. Could suggest a default based on `tools_list` (iterative tools → higher default).
- [ ] Bulk updates from a markdown spec — batch file of `{agent: ..., identity_md: ..., tools_code: ...}` entries fed through `edit_agent`.
- [ ] Registry migration on startup — pre-v0.5.0 entries missing `updated_at` / `max_turns` / `max_budget_usd` / `permission_mode` get backfilled. Currently tolerant-read only.

## Deferred by design

- [ ] `test_agent` still makes real SDK calls (bills). No pure-offline smoke mode. Trade-off: full-fidelity testing vs free CI. Current choice is full-fidelity; if cost becomes an issue, revisit.
- [ ] Generated agents all share the same template. Template variants (minimal / full / iterative) could let users pick a weight class, but YAGNI until a concrete need emerges.

## Notes

- Kept `output/ez-read/` as a real-world repair case study — it was broken by the pre-v0.5.1 scaffold flow and fixed in-place.
- Logs in `agent_builder/logs/` and `.bak-*` files are gitignored but still accumulate on disk; `--sweep` handles them.
- `audit.md` at the repo root is the record of the pre-release code review. Keep as-is until v0.8.0 ships, then either move to `docs/` or collapse into CHANGELOG.
