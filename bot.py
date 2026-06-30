import asyncio
import datetime
import sys
import os
from datetime import timezone, timedelta
from aiohttp import web
from pyrogram import Client, filters, enums, __version__ as pyrogram_version
from pyrogram.types import Message, BotCommand
from pyrogram.errors import FloodWait, RPCError
from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL, ADMINS
from database.db import db
import log
from log import LOGGER, setup_telegram_logging, stop_telegram_logging
from pyrogram import utils as pyroutils

pyroutils.MIN_CHAT_ID = -999999999999
pyroutils.MIN_CHANNEL_ID = -100999999999999
logger = LOGGER(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

USER_CACHE = set()

LOGO = r"""
  ██████╗  ██╗  ██╗  █████╗  ███╗   ██╗ ██████╗   █████╗  ██╗      
  ██╔══██╗ ██║  ██║ ██╔══██╗ ████╗  ██║ ██╔══██╗ ██╔══██╗ ██║      
  ██║  ██║ ███████║ ███████║ ██╔██╗ ██║ ██████╔╝ ███████║ ██║      
  ██║  ██║ ██╔══██║ ██╔══██║ ██║╚██╗██║ ██╔═══╝  ██╔══██║ ██║      
  ██████╔╝ ██║  ██║ ██║  ██║ ██║ ╚████║ ██║      ██║  ██║ ███████
    𝙱𝙾𝚃 𝚆𝙾𝚁𝙺𝙸𝙽𝙶 𝙿𝚁𝙾𝙿𝙴𝚁𝙻𝚈....
"""

# ─── Health Check Server ────────────────────────────────────────────────────

async def health_handler(request):
    return web.Response(text="OK", status=200)

async def restart_handler(request):
    logger.info("Restart triggered via HTTP /restart endpoint")
    # Schedule the restart after sending the response so the client gets a reply
    async def _do_restart():
        await asyncio.sleep(1)
        try:
            await request.app["bot_instance"].send_message(
                LOG_CHANNEL,
                "🔄 <b>Bot is restarting via HTTP /restart endpoint...</b>"
            )
        except Exception:
            pass
        os.execl(sys.executable, sys.executable, *sys.argv)

    asyncio.create_task(_do_restart())
    return web.Response(text="Restarting bot...", status=200)

async def start_health_server(bot_instance):
    app = web.Application()
    app["bot_instance"] = bot_instance
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/restart", restart_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server running on port {port}")

# ─── Watchdog ───────────────────────────────────────────────────────────────

async def watchdog(bot: "Bot", interval: int = 300, max_failures: int = 3):
    """
    Pings Telegram every `interval` seconds.
    If `max_failures` consecutive pings fail, forces a process restart so
    Koyeb can bring the container back up cleanly.
    """
    from pyrogram import raw
    failures = 0
    await asyncio.sleep(60)  # grace period after startup
    while True:
        try:
            await asyncio.wait_for(
                bot.invoke(raw.functions.Ping(ping_id=0)),
                timeout=30
            )
            failures = 0
            logger.debug("Watchdog ping OK")
        except Exception as e:
            failures += 1
            logger.warning(f"Watchdog ping failed ({failures}/{max_failures}): {e}")
            if failures >= max_failures:
                logger.error("Watchdog: session unrecoverable — forcing process exit for Koyeb restart.")
                try:
                    await bot.send_message(
                        LOG_CHANNEL,
                        "⚠️ <b>Watchdog detected dead session. Restarting...</b>"
                    )
                except Exception:
                    pass
                os._exit(1)
        await asyncio.sleep(interval)

# ────────────────────────────────────────────────────────────────────────────

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="cantarella_Login_Bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="cantarella"),
            workers=4,                    # reduced from 10 — fewer concurrent readers = less race risk
            sleep_threshold=15,
            max_concurrent_transmissions=2,  # reduced from 5
            ipv6=False,
            in_memory=False,
        )
        self._watchdog_task: asyncio.Task | None = None

    async def start(self):
        print(LOGO)

        # 1. Start health check server (pass self so /restart can notify LOG_CHANNEL)
        try:
            await start_health_server(self)
        except Exception as e:
            logger.warning(f"Health server failed to start: {e}")

        # 2. Resilient login loop
        while True:
            try:
                await super().start()
                break
            except FloodWait as e:
                wait_time = int(e.value) + 10
                logger.warning(f"FLOOD_WAIT during login. Sleeping {wait_time}s...")
                await asyncio.sleep(wait_time)
            except Exception as e:
                logger.error(f"Critical Startup Error: {e}")
                await asyncio.sleep(15)

        # 3. Activate pyrogram → Telegram log forwarding
        setup_telegram_logging(self)

        me = await self.get_me()

        # 4. DB Stats
        try:
            user_count = await db.total_users_count()
            logger.info(f"MongoDB Connected: {user_count} users found.")
        except Exception as e:
            logger.error(f"DB stats failed: {e}")
            user_count = "Unknown"

        # 5. Startup notification
        now = datetime.datetime.now(IST)
        startup_text = (
            f"<b><i>🤖 Bot Successfully Started ♻️</i></b>\n\n"
            f"<b>Bot:</b> @{me.username}\n"
            f"<b>Users:</b> <code>{user_count} / 200</code>\n"
            f"<b>Time:</b> <code>{now.strftime('%I:%M %p')} IST</code>\n\n"
            f"<b>Developed by @cantarellabots</b>"
        )
        try:
            await self.send_message(LOG_CHANNEL, startup_text)
            logger.info("Startup log sent.")
        except Exception as e:
            logger.error(f"Failed to send startup log: {e}")

        await self.set_bot_commands_list()

        # 6. Start watchdog AFTER everything else is ready
        self._watchdog_task = asyncio.create_task(watchdog(self))
        logger.info("Watchdog started.")

    async def stop(self, *args):
        # Cancel watchdog first so it doesn't fire during shutdown
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

        stop_telegram_logging()

        try:
            await self.send_message(LOG_CHANNEL, "<b><i>❌ Bot is going Offline</i></b>")
        except Exception:
            pass

        await asyncio.shield(super().stop())
        logger.info("Bot stopped cleanly")

    async def set_bot_commands_list(self):
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Show help"),
            BotCommand("login", "Login"),
            BotCommand("logout", "Logout"),
            BotCommand("cancel", "Cancel current action"),
            BotCommand("myplan", "Check your plan"),
            BotCommand("premium", "Premium info"),
            BotCommand("setchat", "Set target chat"),
            BotCommand("set_thumb", "Set thumbnail"),
            BotCommand("view_thumb", "View thumbnail"),
            BotCommand("del_thumb", "Delete thumbnail"),
            BotCommand("set_caption", "Set caption"),
            BotCommand("see_caption", "View caption"),
            BotCommand("del_caption", "Delete caption"),
            BotCommand("set_del_word", "Add delete word"),
            BotCommand("rem_del_word", "Remove delete word"),
            BotCommand("set_repl_word", "Add replace word"),
            BotCommand("rem_repl_word", "Remove replace word"),
        ]
        await self.set_bot_commands(commands)


BotInstance = Bot()


@BotInstance.on_message(filters.private & filters.incoming, group=-1)
async def new_user_log(bot: Client, message: Message):
    user = message.from_user
    if not user or user.id in USER_CACHE:
        return

    if not await db.is_user_exist(user.id):
        await db.add_user(user.id, user.first_name)

        now = datetime.datetime.now(IST)
        log_text = (
            f"<b>#NewUser 👤</b>\n"
            f"<b>User:</b> {user.mention}\n"
            f"<b>ID:</b> <code>{user.id}</code>\n"
            f"<b>Time:</b> {now.strftime('%I:%M %p')} IST"
        )
        try:
            await bot.send_message(LOG_CHANNEL, log_text)
        except Exception:
            pass

    USER_CACHE.add(user.id)


@BotInstance.on_message(filters.command("cmd") & filters.user(ADMINS))
async def update_commands(bot: Client, message: Message):
    try:
        await bot.set_bot_commands_list()
        await message.reply_text("✅ Commands menu updated!")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")


if __name__ == "__main__":
    BotInstance.run()
