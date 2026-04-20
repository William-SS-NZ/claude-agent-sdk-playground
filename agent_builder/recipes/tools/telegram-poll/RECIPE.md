---
name: telegram-poll
type: tool
version: 0.1.1
description: Long-polls Telegram bot API for incoming messages, exposes an async iterator of Incoming records.
when_to_use: Agent runs in poll mode and should react to Telegram DMs without exposing a public webhook.
env_keys:
  - name: TELEGRAM_BOT_TOKEN
    description: Token from @BotFather.
    example: "1234567890:ABC-DEF..."
  - name: TELEGRAM_ALLOWED_SENDER_IDS
    description: Comma-separated list of numeric Telegram user IDs allowed to message the bot. Others are ignored.
    example: "123456789,987654321"
allowed_tools_patterns:
  - mcp__agent_tools__telegram_send
tags: [telegram, messaging, poll]
poll_source: true
---

# Telegram Poll

Provides two things for a poll-mode agent:

1. An async generator `telegram_poll_source()` that yields `Incoming` records (sender_id, text, media_refs, raw) from every incoming message on the configured bot, filtered to senders in `TELEGRAM_ALLOWED_SENDER_IDS`.
2. An MCP tool `telegram_send(chat_id, text)` the agent can call to reply.

## Caveats

- First unknown sender triggers one INFO log line (`ignored message from <id>`); no reply is sent.
- Photos arrive as `media_refs: [{"kind": "photo", "file_id": "..."}]`. The agent resolves them to bytes via a separate `telegram_fetch_media` tool (shipped separately when needed) or via a generic fetch helper.
- `run_polling()` blocks; the tool wraps it in an async generator so the agent's main loop can iterate naturally.
- Requires `python-telegram-bot>=21.0` — installed via the `[telegram]` extra: `pip install -e ".[dev,telegram]"`.
