# TODO

Outstanding work for future sessions. Not everything here is a bug — some are polish, some are quality-of-life, some are deferred by design.

## Shipped in v0.7.0

- [x] ~~`--sweep` CLI flag~~ — cleans `.bak-<ts>` files, per-run builder logs, repo-root `screenshots/`. `--older-than DAYS` (default 7).
- [x] ~~`--doctor` CLI flag~~ — registry integrity, orphan output dirs, template placeholder drift, missing identity files, unfilled scaffold placeholders.
- [x] ~~`GENERATED_WITH_BUILDER_VERSION` stamp~~ — every generated agent carries the builder version it was scaffolded with.
- [x] ~~Hardcoded `version="1.0.0"` drift~~ — `agent_builder/_version.py` is now the single source of truth.
- [x] ~~Spec-file-format epilog on generated agent `--help`~~.
- [x] ~~AST regression test for cli_mode wiring~~.
- [x] ~~Menu options 2-6 short-circuit when registry empty~~.

## High-priority, not yet scheduled

- [x] ~~Confirm CI passes on GitHub Actions for v0.4.x / v0.5.x / v0.6.0.~~ Confirmed green by user 2026-04-19.
- [ ] `python -m build` smoke test — verify `PolyForm-Noncommercial-1.0.0` passes modern setuptools license-classifier validation without warnings. Blocks any future PyPI publish.
- [ ] `make setup` / one-shot onboarding script — new contributor clones, runs one command, gets hooks activated + editable install + test run. Currently three manual steps.

## Polish / nice-to-have

- [ ] Builder's own `MEMORY.md` never updates itself. Every agent build / edit / remove could be logged back so the builder "remembers" what it's done across sessions. Today it just sits static.
- [ ] Builder has no `USER.md` — user identity / preferences aren't personalised. Could match the generated-agent contract (optional `USER.md` loaded if present).
- [ ] Generated agents' `--help` currently has no link to the generated agent's own README or docs (they don't have one). If future builds include a README, wire it into help output.
- [ ] Self-heal's audit log (`agent_builder/self-heal.log`) has no UI for browsing — only raw tail. A `--show-self-heals [--last N]` CLI flag would expose it.
- [ ] Rollback tool handles one backup at a time. Batch rollback (`rollback all backups from today`) would help recover from a bad multi-file self-heal.
- [ ] No way to diff before applying a self-heal — user sees snippets but not a full unified diff. Could show `difflib.unified_diff` output.
- [ ] Registry has no concept of "agent status" beyond the free-text `status` field. Could add structured states (`draft`, `active`, `archived`, `broken`) with lifecycle transitions.
- [ ] `test_agent` max_turns has to be guessed per agent. Could suggest a default based on `tools_list` (iterative tools → higher default).

## Deferred by design

- [ ] Web tools (`WebFetch` / `WebSearch`) are always on. Could gate behind a flag for privacy-sensitive or offline builds. Currently trusting the user's environment.
- [ ] `test_agent` still makes real SDK calls (bills). No pure-offline smoke mode. Trade-off: full-fidelity testing vs free CI. Current choice is full-fidelity; if cost becomes an issue, revisit.
- [ ] Generated agents all share the same template. Template variants (minimal / full / iterative) could let users pick a weight class, but YAGNI until a concrete need emerges.

## Notes

- Kept `output/ez-read/` as a real-world repair case study — it was broken by the pre-v0.5.1 scaffold flow and fixed in-place.
- Logs in `agent_builder/logs/` and `.bak-*` files are gitignored but still accumulate on disk; `--sweep` (in progress) handles them.
