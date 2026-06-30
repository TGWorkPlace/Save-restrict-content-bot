import logging
import os
import asyncio
from pyrogram import Client

LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "-1003129760888"))


class TelegramLogHandler(logging.Handler):
    """
    A logging.Handler that queues log records and ships them to
    LOG_CHANNEL as Telegram messages via the bot client.

    Only records from pyrogram.* loggers are forwarded.
    Everything is sent through an asyncio.Queue so the handler
    never blocks the event loop and never crashes if the send fails.
    """

    def __init__(self, client: Client, channel_id: int, level=logging.WARNING):
        super().__init__(level)
        self.client     = client
        self.channel_id = channel_id
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Call this once after the bot's event loop is running
    # ------------------------------------------------------------------
    def start(self):
        """Spawn the background sender coroutine."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._sender())

    def stop(self):
        """Cancel the background task on shutdown."""
        if self._task and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------
    # logging.Handler interface
    # ------------------------------------------------------------------
    def emit(self, record: logging.LogRecord):
        # Only forward pyrogram logs
        if not record.name.startswith("pyrogram"):
            return
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            pass  # drop silently rather than block

    # ------------------------------------------------------------------
    # Background coroutine — reads queue and sends to Telegram
    # ------------------------------------------------------------------
    async def _sender(self):
        while True:
            try:
                record: logging.LogRecord = await self._queue.get()
                text = self._format_record(record)
                try:
                    await self.client.send_message(
                        chat_id=self.channel_id,
                        text=text,
                        parse_mode=None,   # plain text — log lines can contain special chars
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass  # never let a send failure kill the loop
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def _format_record(self, record: logging.LogRecord) -> str:
        level_icon = {
            logging.DEBUG:    "🔍 DEBUG",
            logging.INFO:     "ℹ️ INFO",
            logging.WARNING:  "⚠️ WARNING",
            logging.ERROR:    "❌ ERROR",
            logging.CRITICAL: "🔴 CRITICAL",
        }.get(record.levelno, record.levelname)

        msg = self.format(record)

        # Telegram messages are capped at 4096 chars
        max_body = 4096 - 200
        if len(msg) > max_body:
            msg = msg[:max_body] + "\n… (truncated)"

        return (
            f"[PYROGRAM LOG]\n"
            f"Level  : {level_icon}\n"
            f"Logger : {record.name}\n"
            f"{'─' * 30}\n"
            f"{msg}"
        )


# ---------------------------------------------------------------------------
# Public factory used by the rest of the project
# ---------------------------------------------------------------------------

def LOGGER(name: str) -> logging.Logger:
    """
    Drop-in replacement for a plain logging.getLogger call.

    Usage (same as before):
        from logger import LOGGER
        logger = LOGGER(__name__)
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# ---------------------------------------------------------------------------
# setup_telegram_logging — call once inside your bot's startup, e.g. in
# __main__.py after `await app.start()`
# ---------------------------------------------------------------------------

_telegram_handler: TelegramLogHandler | None = None


def setup_telegram_logging(client: Client, level: int = logging.WARNING):
    """
    Attach a TelegramLogHandler to the root pyrogram logger so every
    pyrogram WARNING / ERROR / CRITICAL goes to LOG_CHANNEL.

    Call this once after the Pyrogram client has started:

        from logger import setup_telegram_logging
        await app.start()
        setup_telegram_logging(app)
    """
    global _telegram_handler

    if not LOG_CHANNEL:
        logging.getLogger(__name__).warning(
            "LOG_CHANNEL is not set — Telegram log forwarding disabled."
        )
        return

    pyrogram_root = logging.getLogger("pyrogram")

    # Avoid attaching the handler twice on hot-reload
    for h in pyrogram_root.handlers:
        if isinstance(h, TelegramLogHandler):
            return

    _telegram_handler = TelegramLogHandler(client, LOG_CHANNEL, level=level)
    _telegram_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(name)s\n%(message)s"
    ))

    pyrogram_root.addHandler(_telegram_handler)
    pyrogram_root.setLevel(min(pyrogram_root.level or logging.WARNING, level))

    _telegram_handler.start()


def stop_telegram_logging():
    """Call on shutdown to flush the queue and cancel the sender task."""
    global _telegram_handler
    if _telegram_handler:
        _telegram_handler.stop()
        _telegram_handler = None
