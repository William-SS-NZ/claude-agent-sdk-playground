# OAuth Setup for MCP Recipes

Some MCP recipes (Google Calendar, Notion, Linear, etc.) need OAuth2 access to a user account before the agent can call them. The recipe ships a `setup_auth.py.tmpl` that attach_recipe materializes into your agent dir as `setup_auth.py`. Run it once; the agent reuses the resulting refresh token on every subsequent run.

## Google Calendar — worked example

1. Go to https://console.cloud.google.com — create a new project.
2. APIs & Services → Enable APIs and Services → search "Google Calendar API" → Enable.
3. APIs & Services → OAuth consent screen:
   - User type: External
   - App name: anything
   - Add scope: `https://www.googleapis.com/auth/calendar`
   - Add your own email as a test user (required while the app is in "Testing" state)
4. APIs & Services → Credentials → Create Credentials → OAuth client ID:
   - Application type: Desktop app
   - Download the JSON. Rename to `credentials.json` and save it in `output/<agent-name>/`.
5. Edit `output/<agent-name>/.env`:

    ```
    GOOGLE_OAUTH_CLIENT_SECRETS=./credentials.json
    GOOGLE_OAUTH_TOKEN_PATH=./token.json
    ```

6. `cd output/<agent-name> && python setup_auth.py`. A browser window opens; grant access.
7. The script prints `OK - token written to ./token.json`. You're done.

From now on, `python agent.py` has Calendar tools available as `mcp__gcal__*`.

## Troubleshooting

**"access_denied" in the browser**
Add your own email as a test user in the OAuth consent screen (step 3).

**"invalid_client"**
Double-check `GOOGLE_OAUTH_CLIENT_SECRETS` points at the correct JSON. The file should contain `"installed": {"client_id": ..., "client_secret": ...}`.

**"token expired / revoked"**
Delete `token.json` and re-run `setup_auth.py`.

**Scope change**
If you add scopes to the recipe, delete `token.json` and re-run — old tokens don't cover new scopes.

## Adding a new OAuth provider recipe

Follow the pattern of `agent_builder/recipes/mcps/google-calendar/`:
1. Write `RECIPE.md` with `oauth_scopes:` populated.
2. Declare two env keys in order: client secrets path, then token path.
3. Write `setup_auth.py.tmpl` using the four placeholders (`{{scopes}}`, `{{client_secrets_env}}`, `{{token_path_env}}`, `{{recipe_name}}`).
4. Write `mcp.json` with `env_passthrough` listing the env keys the MCP subprocess needs.

The skill-creator sub-plan (Phase G) adds a recipe-author guide — link from here when it lands.
