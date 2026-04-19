---
name: google-calendar
type: mcp
version: 0.1.0
description: Read/write Google Calendar events via the Google Calendar MCP server.
when_to_use: Agent creates, updates, reads, or deletes calendar events on behalf of the user.
env_keys:
  - name: GOOGLE_OAUTH_CLIENT_SECRETS
    description: Path to OAuth client JSON downloaded from Google Cloud Console.
    example: ./credentials.json
  - name: GOOGLE_OAUTH_TOKEN_PATH
    description: Where setup_auth.py writes the refresh token JSON (gitignored by default).
    example: ./token.json
oauth_scopes:
  - https://www.googleapis.com/auth/calendar
allowed_tools_patterns:
  - mcp__gcal__*
tags: [calendar, google, oauth]
---

# Google Calendar MCP

Full setup steps, OAuth consent screen notes, and troubleshooting live in `docs/oauth-setup.md`. The short version:

1. Google Cloud Console -> new project -> enable Calendar API -> OAuth consent screen -> add the `calendar` scope.
2. Download the OAuth client JSON, save it next to the agent as `credentials.json`.
3. Set `GOOGLE_OAUTH_CLIENT_SECRETS=./credentials.json` and `GOOGLE_OAUTH_TOKEN_PATH=./token.json` in the agent's `.env`.
4. Run `python setup_auth.py` once. Browser opens, grant access, done.

After that, `python agent.py` has Calendar tools available as `mcp__gcal__*`.

## Package choice

The `mcp.json` points at `@cocal/google-calendar-mcp` (npm) — chosen after a survey of the npm registry in April 2026: it is the most actively maintained community Google Calendar MCP (v2.6.x, published March 2026, ~60k monthly downloads) and uses MIT license. Source: https://github.com/nspady/google-calendar-mcp. There is no first-party Google / modelcontextprotocol.io server for Calendar at this time.

Note on env var names: the upstream server reads `GOOGLE_OAUTH_CREDENTIALS` (credentials JSON path) and `GOOGLE_CALENDAR_MCP_TOKEN_PATH` (token storage). This recipe exposes a stable local-name pair (`GOOGLE_OAUTH_CLIENT_SECRETS` / `GOOGLE_OAUTH_TOKEN_PATH`) that `setup_auth.py` uses directly; `mcp.json`'s `env_passthrough` forwards both the local names and the upstream-expected names so the subprocess sees whichever pair the user set. Keep both pairs pointing at the same files, or set only the local pair and the recipe's loader will alias them.
