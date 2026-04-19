"""telegram-poll recipe — exposes telegram_poll_source + telegram_send.

Each tool recipe is its own in-process MCP server: the ``tools_server`` at the
bottom of this module is picked up by ``attach_recipe`` which wires it into the
agent as a dedicated recipe server (``mcp__telegram-poll__telegram_send``).

The TOOLS_HEADER (imports + ``_test_mode()`` helper) lives in the *agent's*
tools.py for its bespoke tools. This recipe file ships self-contained — it
imports only what it needs from ``claude_agent_sdk`` and provides its own
``_test_mode()`` helper so it can be copied standalone if a downstream agent
prefers to vendor it.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field

from claude_agent_sdk import tool, create_sdk_mcp_server

try:
    from telegram import Update
    from telegram.ext import Application, MessageHandler, filters
except ImportError:  # pragma: no cover
    Application = None  # type: ignore
    Update = None  # type: ignore
    MessageHandler = None  # type: ignore
    filters = None  # type: ignore


logger = logging.getLogger(__name__)


def _test_mode() -> bool:
    """Return True when AGENT_TEST_MODE env is set — flipped by test_agent."""
    return os.environ.get("AGENT_TEST_MODE") == "1"


@dataclass
class Incoming:
    sender_id: int
    chat_id: int
    text: str
    media_refs: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def _allowed_sender_ids() -> set[int]:
    raw = os.environ.get("TELEGRAM_ALLOWED_SENDER_IDS", "").strip()
    if not raw:
        return set()
    return {int(x) for x in raw.split(",") if x.strip()}


async def telegram_poll_source(queue: "asyncio.Queue[Incoming] | None" = None):
    """Async generator yielding Incoming for every authorized message."""
    if Application is None:
        raise RuntimeError(
            "python-telegram-bot not installed. pip install -e '.[telegram]' to enable poll mode."
        )
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    allowed = _allowed_sender_ids()
    q: "asyncio.Queue[Incoming]" = queue if queue is not None else asyncio.Queue()

    async def _handle(update, _context):
        msg = update.effective_message
        if msg is None or update.effective_user is None:
            return
        if allowed and update.effective_user.id not in allowed:
            logger.info("ignored message from %s", update.effective_user.id)
            return
        media_refs: list[dict] = []
        if msg.photo:
            biggest = max(msg.photo, key=lambda p: p.width * p.height)
            media_refs.append({"kind": "photo", "file_id": biggest.file_id})
        if msg.document:
            media_refs.append({"kind": "document", "file_id": msg.document.file_id})
        await q.put(Incoming(
            sender_id=update.effective_user.id,
            chat_id=update.effective_chat.id if update.effective_chat else update.effective_user.id,
            text=msg.text or msg.caption or "",
            media_refs=media_refs,
            raw=update.to_dict(),
        ))

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.ALL, _handle))

    async def _run_app():
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

    runner = asyncio.create_task(_run_app())
    try:
        while True:
            yield await q.get()
    finally:
        runner.cancel()
        try:
            await app.updater.stop()
        except Exception:  # pragma: no cover — best-effort shutdown
            pass


@tool(
    "telegram_send",
    "Send a text message back to a Telegram chat.",
    {
        "type": "object",
        "properties": {
            "chat_id": {"type": "integer"},
            "text": {"type": "string"},
        },
        "required": ["chat_id", "text"],
    },
)
async def telegram_send(args):
    if _test_mode():
        return {"content": [{"type": "text", "text": f"[mock] send {args['text']!r} to {args['chat_id']}"}]}
    if Application is None:
        return {"content": [{"type": "text", "text": "python-telegram-bot not installed"}], "is_error": True}
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    async with app:
        await app.bot.send_message(chat_id=args["chat_id"], text=args["text"])
    return {"content": [{"type": "text", "text": "sent"}]}


# Each tool recipe is its own MCP server. attach_recipe imports this
# `tools_server` and wires it into the agent as a dedicated recipe server.
tools_server = create_sdk_mcp_server(
    name="telegram-poll",
    version="0.1.0",
    tools=[telegram_send],
)
