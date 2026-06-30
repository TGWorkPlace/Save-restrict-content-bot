# Developed by: LastPerson07 × cantarella
# Telegram: @cantarellabots | @THEUPDATEDGUYS
import os
import asyncio
import random
import time
import shutil
import pyrogram
import requests
import hashlib
from pyrogram import Client, filters, enums
from pyrogram.errors import (
    FloodWait, UserIsBlocked, InputUserDeactivated, UserAlreadyParticipant,
    InviteHashExpired, UsernameNotOccupied, AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, InputMediaPhoto
from config import API_ID, API_HASH, ERROR_MESSAGE, ADMINS
from database.db import db
import math
from logger import LOGGER

# --- Import additional features from additional.py ---
# NOTE: bad-words, prefix/suffix, metadata and sleep settings are no longer
# hard-coded globals - they're fetched per-user from the database below and
# passed into these now-parametrized helper functions.
from cantarella.additional import (
    clean_filename,
    apply_prefix_suffix,
    smart_sleep,
    download_thumbnail,
    add_metadata_with_ffmpeg,
)

DEFAULT_SLEEP_VALUES = [318, 324, 333, 338, 349, 352, 361, 367, 376, 384]


async def _forward_to_dump_chat(client: Client, user_id: int, sent_message):
    """Copy a just-saved message into the user's configured dump chat, if any.
    This is what actually makes /setchat have an effect - previously the
    dump_chat value was saved to the DB but nothing ever read it back."""
    if not sent_message:
        return
    try:
        dump_chat_id = await db.get_dump_chat(user_id)
    except Exception:
        return
    if not dump_chat_id:
        return
    try:
        await sent_message.copy(dump_chat_id)
    except Exception as e:
        logger.error(f"Failed to forward saved content to dump chat {dump_chat_id} for user {user_id}: {e}")

logger = LOGGER(__name__)
SUBSCRIPTION = os.environ.get('SUBSCRIPTION', 'https://graph.org/file/242b7f1b52743938d81f1.jpg')
FREE_LIMIT_SIZE = 2 * 1024 * 1024 * 1024
FREE_LIMIT_DAILY = 10
UPI_ID = os.environ.get("UPI_ID", "your_upi@oksbi")
QR_CODE = os.environ.get("QR_CODE", "https://graph.org/file/242b7f1b52743938d81f1.jpg")
REACTIONS = [
    "👍", "❤️", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", "🤬",
    "😢", "🎉", "🤩", "🤮", "💩", "🙏", "👌", "🕊", "🤡", "🥱",
    "🥴", "😍", "🐳", "❤️‍🔥", "🌚", "🌭", "💯", "🤣", "⚡", "🍌",
    "🏆", "💔", "🤨", "😐", "🍓", "🍾", "💋", "🖕", "😈", "😴",
    "😭", "🤓", "👻", "👨‍💻", "👀", "🎃", "🙈", "😇", "😨", "🤝",
    "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪", "🗿", "🆒",
    "💘", "🙉", "🦄", "😘", "💊", "🙊", "😎", "👾", "🤷‍♂️", "🤷‍♀️",
    "😡"
]

dev_text = "👨‍💻 Mind Behind This Bot:\n• @DmOwner\n• @akaza7902"
expected_dev_hash = "b9e63b7578bdec13f3cb3162fe5f5e93dccaba3bfd5c8ddacbb90ffdcdcce402"
channels_text = "📢 Official Channels:\n• @ReX_update\n• @THEUPDATEDGUYS\n\nStay updated for new features!"
expected_channels_hash = "e19212e571bd0f6626450dd790029d392c0748c554d4b386a0c0752f4148d37d"

if (
    hashlib.sha256(dev_text.encode('utf-8')).hexdigest() != expected_dev_hash or
    hashlib.sha256(channels_text.encode('utf-8')).hexdigest() != expected_channels_hash
):
    raise Exception("Tampered developer info detected! Bot will not start. Fuck the code - crashing now.")


# ===========================================================================
# Custom exception for cancellation
# ===========================================================================

class ProcessCancelled(Exception):
    """Raised when the user cancels an ongoing task."""
    pass


# ===========================================================================
# Task registry
# ===========================================================================

class batch_temp(object):
    IS_BATCH       = {}   # True  → slot free, False → task running
    CANCEL_TASKS   = {}   # True  → cancellation requested
    DOWNLOAD_TASKS = {}   # asyncio.Task references for in-flight downloads
    ACTIVE_SESSIONS = {}  # reusable pyrogram Client objects per user


def get_task_key(user_id: int, chat_id: int) -> str:
    return f"{user_id}:{chat_id}"


# ===========================================================================
# Script strings
# ===========================================================================

class script(object):

    START_TXT = """<b>👋 Hello {},</b>
<b>🤖 I am <a href=https://t.me/{}>{}</a></b>
<i>Your Professional Restricted Content Saver Bot.</i>
<blockquote><b>🚀 System Status: 🟢 Online</b>
<b>⚡ Performance: 10x High-Speed Processing</b>
<b>🔐 Security: End-to-End Encrypted</b>
<b>📊 Uptime: 99.9% Guaranteed</b></blockquote>
<b>👇 Select an Option Below to Get Started:</b>
"""
    HELP_TXT = """<b>📚 Comprehensive Help & User Guide</b>
<blockquote><b>1️⃣ Public Channels (No Login Required)</b></blockquote>
• Forward or send the post link directly.
• Compatible with any public channel or group.
• <i>Example Link:</i> <code>https://t.me/channel/123</code>
<blockquote><b>2️⃣ Private/Restricted Channels (Login Required)</b></blockquote>
• Use <code>/login</code> to securely connect your Telegram account.
• Send the private link (e.g., <code>t.me/c/123...</code>).
• Bot accesses content using your authenticated session.
<blockquote><b>3️⃣ Batch Downloading Mode</b></blockquote>
• Initiate with <code>/batch</code> for multiple files.
• Follow interactive prompts for seamless processing.
<blockquote><b>🛑 Free User Limitations:</b></blockquote>
• <b>Daily Quota:</b> 10 Files / 24 Hours
• <b>File Size Cap:</b> 2GB Maximum
<blockquote><b>💎 Premium Membership Benefits:</b></blockquote>
• Unlimited Downloads & No Restrictions.
• Priority Support & Advanced Features.
<blockquote><b>🕐 Batch Sleep Settings:</b></blockquote>
• Use <code>/setsleep 3 5 7 10</code> to set custom delay between downloads.
• Use <code>/getsleep</code> to view your current sleep settings.
<blockquote><b>👥 Group Support:</b></blockquote>
• Send a Telegram link directly in any group where the bot is a member.
• <code>/cancel</code> and <code>/setsleep</code> work in groups too!
"""
    ABOUT_TXT = """<b>ℹ️ About This Bot</b>
<blockquote><b>╭────[ 🧩 Technical Stack ]────⍟</b>
<b>├⍟ 🤖 Bot Name : <a href=http://t.me/THEUPDATEDGUYS_Bot>Save Content</a></b>
<b>├⍟ 👨‍💻 Developer : <a href=https://t.me/DmOwner>Ⓜ️ark X cantarella</a></b>
<b>├⍟ 📚 Library : <a href='https://docs.pyrogram.org/'>Pyrogram Async</a></b>
<b>├⍟ 🐍 Language : <a href='https://www.python.org/'>Python 3.11+</a></b>
<b>├⍟ 🗄 Database : <a href='https://www.mongodb.com/'>MongoDB Atlas Cluster</a></b>
<b>├⍟ 📡 Hosting : Dedicated High-Speed VPS</b>
<b>╰───────────────⍟</b></blockquote>
"""
    PREMIUM_TEXT = """<b>💎 Premium Membership Plans</b>
<b>Unlock Unlimited Access & Advanced Features!</b>
<blockquote><b>✨ Key Benefits:</b>
<b>♾️ Unlimited Daily Downloads</b>
<b>📂 Support for 4GB+ File Sizes</b>
<b>⚡ Instant Processing (Zero Delay)</b>
<b>🖼 Customizable Thumbnails</b>
<b>📝 Personalized Captions</b>
<b>🛂 24/7 Priority Support</b></blockquote>
<blockquote><b>💳 Pricing Options:</b></blockquote>
• <b>1 Month Plan:</b> ₹50 / $1 (Billed Monthly)
• <b>3 Month Plan:</b> ₹120 / $2.5 (Save 20%)
• <b>Lifetime Access:</b> ₹200 / $4 (One-Time Payment)
<blockquote><b>👇 Secure Payment:</b></blockquote>
<b>💸 UPI ID:</b> <code>{}</code>
<b>📸 QR Code:</b> <a href='{}'>Scan to Pay</a>
<i>After Payment: Send Screenshot to Admin for Instant Activation.</i>
"""
    CAPTION = """<b><a href="https://t.me/THEUPDATEDGUYS"></a></b>\n\n<b>⚜️ Powered By : <a href="https://t.me/THEUPDATEDGUYS">THE UPDATED GUYS 😎</a></b>"""
    LIMIT_REACHED = """<b>🚫 Daily Limit Exceeded</b>
<b>Your 10 free saves for today have been used.</b>
<i>Quota resets automatically after 24 hours from first download.</i>
<blockquote><b>🔓 Upgrade to Premium for Unlimited Access!</b></blockquote>
Remove all restrictions and enjoy seamless downloading.
"""
    SIZE_LIMIT = """<b>⚠️ File Size Exceeded</b>
<b>Free tier limited to 2GB per file.</b>
<blockquote><b>🔓 Upgrade to Premium</b></blockquote>
Download files up to 4GB and beyond with no limits!
"""


# ===========================================================================
# Helpers
# ===========================================================================

def humanbytes(size):
    if not size:
        return "0B"
    power = 2 ** 10
    n = 0
    Dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'


def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
          ((str(hours) + "h, ") if hours else "") + \
          ((str(minutes) + "m, ") if minutes else "") + \
          ((str(seconds) + "s, ") if seconds else "")
    return tmp[:-2] if tmp else "0s"


def get_message_type(msg):
    if getattr(msg, 'document', None):  return "Document"
    if getattr(msg, 'video', None):     return "Video"
    if getattr(msg, 'photo', None):     return "Photo"
    if getattr(msg, 'audio', None):     return "Audio"
    if getattr(msg, 'text', None):      return "Text"
    return None


def make_progress_bar(percentage: float) -> str:
    total_slots = 12
    filled = int(percentage / 100 * total_slots)
    partial = 1 if filled < total_slots and percentage > 0 else 0
    empty = total_slots - filled - partial
    return "[" + "■" * filled + ("▨" if partial else "") + "□" * empty + "]"


# ===========================================================================
# Progress callback — NEVER raises exceptions.
#
# KEY FIX: Pyrogram calls the progress callback from deep inside its internal
# get_file / write loop. Raising ANY exception there (including custom ones)
# causes Pyrogram to log an ERROR traceback and may corrupt the download
# state. Instead, we simply return False when cancelled and let the *caller*
# check CANCEL_TASKS after download_media returns/raises CancelledError.
# ===========================================================================

UPDATE_DELAY = 5   # seconds between progress message edits

async def progress_callback(current, total, smsg, mode, start_time, task_key, file_name="", user_name=""):
    """
    Safe progress callback — returns silently on cancel (never raises).
    Cancellation is propagated by cancelling the asyncio.Task wrapping
    download_media, which causes it to raise asyncio.CancelledError cleanly.
    """
    if smsg is None:
        return

    # ── Silently return if cancelled — do NOT raise here ─────────────────
    if batch_temp.CANCEL_TASKS.get(task_key, False):
        return

    now = time.time()
    cache_attr = f"_last_edit_{smsg.id}"
    last_edit = getattr(progress_callback, cache_attr, 0)
    if now - last_edit < UPDATE_DELAY and current != total:
        return
    setattr(progress_callback, cache_attr, now)

    diff = now - start_time
    percentage = (current / total * 100) if total else 0
    speed = current / diff if diff > 0 else 0
    eta_secs = (total - current) / speed if speed > 0 else 0

    bar = make_progress_bar(percentage)
    elapsed_str = TimeFormatter(int(diff * 1000))
    eta_str = f"{int(eta_secs)}s" if eta_secs > 0 else "-"
    display_name = file_name if file_name else "File"
    status_label = "Download" if mode == "download" else "Upload"
    display_user = user_name if user_name else task_key.split(':')[0]

    text = (
        f"<blockquote><b>{display_name}</b></blockquote>\n"
        f"<blockquote><b>{bar} {percentage:.1f}%</b></blockquote>\n"
        f"<blockquote><b>Processed: {humanbytes(current)} of {humanbytes(total)}</b></blockquote>\n"
        f"<blockquote><b>Status: {status_label} | ETA: {eta_str}</b></blockquote>\n"
        f"<blockquote><b>Speed: {humanbytes(speed)}/s | Elapsed: {elapsed_str}</b></blockquote>\n"
        f"<blockquote><b>Engine: {'Aria2 v1.36.0' if mode == 'download' else 'PyroMulti v2.2.11'}</b></blockquote>\n"
        f"<blockquote><b>Mode:  #Leech | #{'Aria2' if mode == 'download' else 'TG'}</b></blockquote>\n"
        f"<blockquote><b>User: {display_user} | ID: {task_key.split(':')[0]}</b></blockquote>"
    )

    cancel_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("🛑 Cancel", callback_data=f"cancel_{task_key}")
    ]])

    try:
        await smsg.edit_text(text, reply_markup=cancel_markup, parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass


# ===========================================================================
# Internal helper — safely cancel a running download task and wait for it
# ===========================================================================

async def _kill_download_task(task_key: str):
    """
    Cancel the asyncio.Task registered for task_key and wait for it to finish.
    Safe to call even if no task is registered or it's already done.
    """
    task = batch_temp.DOWNLOAD_TASKS.get(task_key)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass
    batch_temp.DOWNLOAD_TASKS.pop(task_key, None)


# ===========================================================================
# Cancel callback — inline button handler
# ===========================================================================

@Client.on_callback_query(filters.regex(r"^cancel_"))
async def cancel_callback(client: Client, callback_query: CallbackQuery):
    data    = callback_query.data
    payload = data[len("cancel_"):]

    if ":" in payload:
        user_id  = int(payload.split(":", 1)[0])
        task_key = payload
    else:
        user_id  = int(payload)
        task_key = payload

    if callback_query.from_user.id != user_id:
        await callback_query.answer("⚠️ This is not your process!", show_alert=True)
        return

    # Mark cancelled first, then kill the task
    batch_temp.CANCEL_TASKS[task_key] = True
    batch_temp.IS_BATCH[task_key]     = True

    await callback_query.answer("🛑 Cancelling…", show_alert=True)

    # Kill in-flight download task
    await _kill_download_task(task_key)

    try:
        await callback_query.message.edit_text(
            "<b>🛑 Cancellation In Progress</b>\n\n"
            "⚠️ Stopping current operation…\n"
            "⚠️ Cleaning up temporary files…",
            parse_mode=enums.ParseMode.HTML
        )
    except Exception:
        pass


# ===========================================================================
# /start
# ===========================================================================

@Client.on_message(filters.command(["start"]) & filters.user(ADMINS))
async def send_start(client: Client, message: Message):
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except Exception:
        pass

    apis = ["https://api.waifu.pics/sfw/waifu", "https://nekos.life/api/v2/img/waifu"]
    try:
        response = requests.get(random.choice(apis))
        response.raise_for_status()
        photo_url = response.json()["url"]
    except Exception as e:
        logger.error(f"Failed to fetch image from API: {e}")
        photo_url = "https://i.postimg.cc/kX9tjGXP/16.png"

    buttons = [
        [
            InlineKeyboardButton("💎 Buy Premium", callback_data="buy_premium"),
            InlineKeyboardButton("🆘 Help & Guide", callback_data="help_btn")
        ],
        [
            InlineKeyboardButton("⚙️ Settings Panel", callback_data="settings_btn"),
            InlineKeyboardButton("ℹ️ About Bot", callback_data="about_btn")
        ],
        [
            InlineKeyboardButton('📢 Channels', callback_data="channels_info"),
            InlineKeyboardButton('👨‍💻 Developers', callback_data="dev_info")
        ]
    ]
    bot = await client.get_me()
    await client.send_photo(
        chat_id=message.chat.id,
        photo=photo_url,
        caption=script.START_TXT.format(message.from_user.mention, bot.username, bot.first_name),
        reply_markup=InlineKeyboardMarkup(buttons),
        reply_to_message_id=message.id,
        parse_mode=enums.ParseMode.HTML
    )


# ===========================================================================
# /help
# ===========================================================================

@Client.on_message(filters.command(["help"]) & (filters.private | filters.group))
async def send_help(client: Client, message: Message):
    buttons = [[InlineKeyboardButton("❌ Close Menu", callback_data="close_btn")]]
    await client.send_message(
        chat_id=message.chat.id,
        text=script.HELP_TXT,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=enums.ParseMode.HTML
    )


# ===========================================================================
# /plan
# ===========================================================================

@Client.on_message(filters.command(["plan", "myplan", "premium"]) & (filters.private | filters.group))
async def send_plan(client: Client, message: Message):
    buttons = [
        [InlineKeyboardButton("📸 Send Payment Proof", url="https://t.me/DmOwner")],
        [InlineKeyboardButton("❌ Close Menu", callback_data="close_btn")]
    ]
    await client.send_photo(
        chat_id=message.chat.id,
        photo=SUBSCRIPTION,
        caption=script.PREMIUM_TEXT.format(UPI_ID, QR_CODE),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=enums.ParseMode.HTML
    )


# ===========================================================================
# /cancel  — command handler (private + group)
# ===========================================================================

@Client.on_message(filters.command(["cancel"]) & (filters.private | filters.group))
async def send_cancel(client: Client, message: Message):
    user_id  = message.from_user.id
    chat_id  = message.chat.id
    task_key = get_task_key(user_id, chat_id)

    if batch_temp.IS_BATCH.get(task_key, True) is True:
        await client.send_message(
            chat_id=message.chat.id,
            text="<b>❌ No Active Process To Cancel.</b>",
            reply_to_message_id=message.id,
            parse_mode=enums.ParseMode.HTML
        )
        return

    # Mark cancelled and free the slot
    batch_temp.CANCEL_TASKS[task_key] = True
    batch_temp.IS_BATCH[task_key]     = True

    # Kill in-flight download task
    await _kill_download_task(task_key)

    await client.send_message(
        chat_id=message.chat.id,
        text=(
            "<b>🛑 Cancelling All Processes Immediately!</b>\n\n"
            "⚠️ Stopping current download/upload…\n"
            "⚠️ Cleaning up temporary files…"
        ),
        reply_to_message_id=message.id,
        parse_mode=enums.ParseMode.HTML
    )


# ===========================================================================
# /setsleep
# ===========================================================================

@Client.on_message(filters.command(["setsleep"]) & (filters.private | filters.group))
async def set_sleep(client: Client, message: Message):
    try:
        parts = message.text.split()[1:]
        if not parts:
            await message.reply(
                "**Usage:** `/setsleep 3 5 7 10`\n\n"
                "Provide space-separated sleep values in seconds.\n"
                "Bot will randomly pick one value for each download to avoid detection.\n\n"
                "**Allowed range:** 1-1000 seconds\n"
                "**Example:** `/setsleep 3 5 7 10 12 15`"
            )
            return

        sleep_values = [int(x) for x in parts if x.isdigit() and 1 <= int(x) <= 1000]
        if not sleep_values:
            await message.reply("❌ Please provide valid sleep values between 1-1000 seconds!")
            return

        # Persist to DB so the setting survives restarts (used to be
        # in-memory only, which meant it reset every time the bot redeployed).
        await db.set_sleep(message.from_user.id, sleep_values)
        await message.reply(
            f"✅ **Sleep values set successfully!**\n\n"
            f"Values: `{', '.join(map(str, sleep_values))}` seconds\n"
            f"Bot will randomly pick one value between downloads.\n\n"
            f"💡 **Tip:** More varied values = better anti-detection!"
        )
    except ValueError:
        await message.reply("❌ Please provide valid numeric values only!")


# ===========================================================================
# /getsleep
# ===========================================================================

@Client.on_message(filters.command(["getsleep"]) & (filters.private | filters.group))
async def get_sleep(client: Client, message: Message):
    sleep_values = await db.get_sleep(message.from_user.id) or DEFAULT_SLEEP_VALUES
    await message.reply(
        f"**⏱️ Current Sleep Settings:**\n\n"
        f"Values: `{', '.join(map(str, sleep_values))}` seconds\n"
        f"Random selection with ±20% jitter for natural behavior.\n\n"
        f"Use `/setsleep` to change these values."
    )


# ===========================================================================
# Settings panel helper
# ===========================================================================

async def settings_panel(client, callback_query):
    user_id    = callback_query.from_user.id
    is_premium = await db.check_premium(user_id)
    badge      = "💎 Premium Member" if is_premium else "👤 Standard User"

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Command List",       callback_data="cmd_list_btn")],
        [InlineKeyboardButton("📊 Usage Stats",        callback_data="user_stats_btn")],
        [InlineKeyboardButton("🗑 Dump Chat Settings", callback_data="dump_chat_btn")],
        [InlineKeyboardButton("🖼 Manage Thumbnail",   callback_data="thumb_btn")],
        [InlineKeyboardButton("📝 Edit Caption",       callback_data="caption_btn")],
        [InlineKeyboardButton("🏷 Prefix / Suffix",    callback_data="prefsuf_info_btn"),
         InlineKeyboardButton("🎬 Metadata",            callback_data="metadata_info_btn")],
        [InlineKeyboardButton("⬅️ Return to Home",     callback_data="start_btn")]
    ])
    text = (
        f"<b>⚙️ Settings Dashboard</b>\n\n"
        f"<b>Account Status:</b> {badge}\n"
        f"<b>User ID:</b> <code>{user_id}</code>\n\n"
        f"<i>Customize and manage your bot preferences below for an optimized experience:</i>"
    )
    await callback_query.edit_message_caption(
        caption=text,
        reply_markup=buttons,
        parse_mode=enums.ParseMode.HTML
    )


# ===========================================================================
# Cleanup helper — removes temp files and optionally deletes the status msg
# ===========================================================================

async def _cleanup(temp_dir: str, file: str = None, smsg=None, delete_smsg: bool = True):
    """Safely remove downloaded file + temp dir, optionally delete status msg."""
    if file and os.path.exists(file):
        try:
            os.remove(file)
        except Exception:
            pass
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
    if smsg and delete_smsg:
        try:
            await smsg.delete()
        except Exception:
            pass


# ===========================================================================
# Main save handler
# ===========================================================================

@Client.on_message(filters.text & (filters.private | filters.group) & ~filters.regex("^/"))
async def save(client: Client, message: Message):
    if "https://t.me/" not in message.text:
        return

    user_id   = message.from_user.id
    chat_id   = message.chat.id
    task_key  = get_task_key(user_id, chat_id)
    user_name = message.from_user.first_name or str(user_id)

    if await filters.private(None, message):
        is_limit_reached = await db.check_limit(user_id)
        if is_limit_reached:
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("💎 Upgrade to Premium", callback_data="buy_premium")]])
            return await message.reply_photo(
                photo=SUBSCRIPTION,
                caption=script.LIMIT_REACHED,
                reply_markup=btn,
                parse_mode=enums.ParseMode.HTML
            )

    if batch_temp.IS_BATCH.get(task_key, True) is False:
        return await message.reply_text(
            "<b>⚠️ A Task is Currently Processing.</b>\n"
            "<i>Please wait for completion or use /cancel to stop.</i>",
            parse_mode=enums.ParseMode.HTML
        )

    datas = message.text.split("/")
    temp  = datas[-1].replace("?single", "").split("-")
    fromID = int(temp[0].strip())
    try:
        toID = int(temp[1].strip())
    except Exception:
        toID = fromID

    batch_temp.IS_BATCH[task_key]     = False
    batch_temp.CANCEL_TASKS[task_key] = False

    total_items = toID - fromID + 1
    completed   = 0

    is_private_link = "https://t.me/c/" in message.text
    is_batch_link   = "https://t.me/b/" in message.text
    is_public_link  = not is_private_link and not is_batch_link

    try:
        for msgid in range(fromID, toID + 1):

            # ── Cancel check at top of every iteration ───────────────────
            if batch_temp.CANCEL_TASKS.get(task_key, False):
                await client.send_message(
                    chat_id=message.chat.id,
                    text=(
                        f"<b>🛑 Batch Process Cancelled!</b>\n\n"
                        f"✅ Completed: {completed}/{total_items} items\n"
                        f"❌ Cancelled at message {msgid}/{toID}"
                    ),
                    reply_to_message_id=message.id,
                    parse_mode=enums.ParseMode.HTML
                )
                break

            if is_public_link:
                username = datas[3]
                try:
                    copied_msg = await client.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=username,
                        message_id=msgid,
                        reply_to_message_id=message.id
                    )
                    await db.add_traffic(user_id)
                    completed += 1
                    await _forward_to_dump_chat(client, user_id, copied_msg)
                except Exception:
                    pass
            else:
                user_data = await db.get_session(user_id)
                if user_data is None:
                    await message.reply(
                        "<b>🔒 Authentication Required</b>\n\n"
                        "<i>Use /login to securely authorize your account.</i>",
                        parse_mode=enums.ParseMode.HTML
                    )
                    batch_temp.IS_BATCH[task_key] = True
                    return

                try:
                    acc = Client(
                        "saverestricted",
                        session_string=user_data,
                        api_hash=API_HASH,
                        api_id=API_ID,
                        in_memory=True,
                        max_concurrent_transmissions=10
                    )
                    await acc.connect()
                except Exception as e:
                    batch_temp.IS_BATCH[task_key] = True
                    return await message.reply(
                        f"<b>❌ Authentication Failed</b>\n\n"
                        f"<i>Your session may have expired. Please /logout and /login again.</i>\n"
                        f"<code>{e}</code>",
                        parse_mode=enums.ParseMode.HTML
                    )

                if is_private_link:
                    chat_target = int("-100" + datas[4])
                elif is_batch_link:
                    chat_target = datas[4]
                else:
                    chat_target = datas[3]

                try:
                    success = await handle_restricted_content(
                        client, acc, message, chat_target, msgid, task_key, user_name
                    )
                    if success:
                        completed += 1
                except ProcessCancelled:
                    await client.send_message(
                        chat_id=message.chat.id,
                        text=(
                            f"<b>🛑 Batch Process Cancelled!</b>\n\n"
                            f"✅ Completed: {completed}/{total_items} items"
                        ),
                        reply_to_message_id=message.id,
                        parse_mode=enums.ParseMode.HTML
                    )
                    break
                except Exception as e:
                    if ERROR_MESSAGE:
                        await client.send_message(
                            message.chat.id,
                            f"Error: {e}",
                            reply_to_message_id=message.id
                        )

            # ── Cancel check before sleep ────────────────────────────────
            if batch_temp.CANCEL_TASKS.get(task_key, False):
                break

            if msgid < toID:
                try:
                    sleep_values = await db.get_sleep(user_id) or DEFAULT_SLEEP_VALUES
                    await smart_sleep(sleep_values)
                except Exception:
                    pass

            if completed > 0 and completed % 5 == 0 and completed < total_items:
                try:
                    await client.send_message(
                        message.chat.id,
                        f"📊 Progress: {completed}/{total_items} completed…",
                        reply_to_message_id=message.id
                    )
                except Exception:
                    pass

    except ProcessCancelled:
        pass
    except Exception as e:
        logger.error(f"Error in batch process: {e}")
    finally:
        batch_temp.IS_BATCH[task_key]     = True
        batch_temp.CANCEL_TASKS[task_key] = False
        batch_temp.DOWNLOAD_TASKS.pop(task_key, None)

        if completed > 0 and not batch_temp.CANCEL_TASKS.get(task_key, False):
            try:
                await client.send_message(
                    message.chat.id,
                    f"✅ <b>Batch Complete!</b>\n\nProcessed: {completed}/{total_items} items",
                    reply_to_message_id=message.id,
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception:
                pass


# ===========================================================================
# handle_restricted_content
# ===========================================================================

async def handle_restricted_content(
    client: Client,
    acc,
    message: Message,
    chat_target,
    msgid: int,
    task_key: str,
    user_name: str = ""
) -> bool:
    """
    Returns True on successful upload, False on skip/error.
    Raises ProcessCancelled if the user cancels mid-way.

    KEY FIX: download_media is wrapped in an asyncio.Task so it can be
    cancelled cleanly via task.cancel() (triggered by /cancel or the inline
    button). The progress callback NEVER raises — cancellation is detected
    after download_media returns by checking CANCEL_TASKS.
    """
    user_id      = message.from_user.id
    display_user = user_name if user_name else (message.from_user.first_name or str(user_id))

    # ── Fetch source message ─────────────────────────────────────────────
    try:
        msg: Message = await acc.get_messages(chat_target, msgid)
    except Exception as e:
        logger.error(f"Error fetching message {msgid}: {e}")
        return False

    if msg.empty:
        return False

    msg_type = get_message_type(msg)
    if not msg_type:
        return False

    # ── File-size gate (free users) ──────────────────────────────────────
    file_size = 0
    if msg_type == "Document": file_size = getattr(msg.document, 'file_size', 0)
    elif msg_type == "Video":  file_size = getattr(msg.video,    'file_size', 0)
    elif msg_type == "Audio":  file_size = getattr(msg.audio,    'file_size', 0)

    if file_size > FREE_LIMIT_SIZE:
        if not await db.check_premium(user_id):
            btn = InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Upgrade to Premium", callback_data="buy_premium")
            ]])
            await client.send_message(
                message.chat.id,
                script.SIZE_LIMIT,
                reply_markup=btn,
                parse_mode=enums.ParseMode.HTML
            )
            return False

    # ── Text messages ────────────────────────────────────────────────────
    if msg_type == "Text":
        try:
            await client.send_message(
                message.chat.id, msg.text,
                entities=msg.entities,
                parse_mode=enums.ParseMode.HTML
            )
            return True
        except Exception:
            return False

    # ── Pre-download cancel check ────────────────────────────────────────
    if batch_temp.CANCEL_TASKS.get(task_key, False):
        raise ProcessCancelled("Cancelled before download")

    await db.add_traffic(user_id)

    # ── Resolve display filename ─────────────────────────────────────────
    display_name = "File"
    if msg_type == "Document" and msg.document:
        display_name = msg.document.file_name or "Document"
    elif msg_type == "Video" and msg.video:
        display_name = msg.video.file_name or "Video"
    elif msg_type == "Audio" and msg.audio:
        display_name = msg.audio.file_name or "Audio"

    cancel_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("🛑 Cancel", callback_data=f"cancel_{task_key}")
    ]])

    smsg = await client.send_message(
        message.chat.id,
        f"<blockquote><b>{display_name}</b></blockquote>\n"
        f"<blockquote><b>[□□□□□□□□□□□□] 0.0%</b></blockquote>\n"
        f"<blockquote><b>Processed: 0 B of {humanbytes(file_size)}</b></blockquote>\n"
        f"<blockquote><b>Status: Download | ETA: -</b></blockquote>\n"
        f"<blockquote><b>Speed: 0.0 B/s | Elapsed: 0s</b></blockquote>\n"
        f"<blockquote><b>Engine: Aria2 v1.36.0</b></blockquote>\n"
        f"<blockquote><b>Mode:  #Leech | #Aria2</b></blockquote>\n"
        f"<blockquote><b>User: {display_user} | ID: {user_id}</b></blockquote>",
        reply_to_message_id=message.id,
        reply_markup=cancel_markup,
        parse_mode=enums.ParseMode.HTML
    )

    temp_dir   = f"downloads/{message.chat.id}_{message.id}_{msgid}"
    os.makedirs(temp_dir, exist_ok=True)
    file       = None
    start_time = time.time()

    # ── DOWNLOAD ─────────────────────────────────────────────────────────
    try:
        dl_task = asyncio.create_task(
            acc.download_media(
                msg,
                file_name=f"{temp_dir}/",
                progress=progress_callback,
                progress_args=(smsg, "download", start_time, task_key, display_name, display_user)
            )
        )
        batch_temp.DOWNLOAD_TASKS[task_key] = dl_task

        try:
            file = await dl_task
        except asyncio.CancelledError:
            raise ProcessCancelled("Download cancelled by user")
        finally:
            batch_temp.DOWNLOAD_TASKS.pop(task_key, None)

    except ProcessCancelled:
        await _cleanup(temp_dir, file, smsg)
        raise

    except Exception as e:
        await _cleanup(temp_dir, file, smsg)
        logger.error(f"Download error for msg {msgid}: {e}")
        return False

    # ── POST-DOWNLOAD cancel check ───────────────────────────────────────
    if batch_temp.CANCEL_TASKS.get(task_key, False):
        await _cleanup(temp_dir, file, smsg)
        raise ProcessCancelled("Cancelled after download")

    # ── Filename cleanup (uses per-user delete-words / prefix / suffix from DB) ──
    if file and os.path.exists(file):
        old_filename   = os.path.basename(file)
        dir_name       = os.path.dirname(file)

        delete_words   = await db.get_delete_words(user_id)
        file_prefix    = await db.get_prefix(user_id)
        file_suffix    = await db.get_suffix(user_id)

        cleaned        = clean_filename(old_filename, delete_words)
        final_filename = apply_prefix_suffix(cleaned, file_prefix, file_suffix)

        if old_filename != final_filename:
            new_path = os.path.join(dir_name, final_filename)
            os.rename(file, new_path)
            file = new_path
    else:
        await _cleanup(temp_dir, file, smsg)
        return False

    actual_size = os.path.getsize(file) if file and os.path.exists(file) else file_size
    size_str    = humanbytes(actual_size)

    # ── METADATA step ────────────────────────────────────────────────────
    try:
        await smsg.edit_text(
            f"<blockquote><b>{final_filename}</b></blockquote>\n"
            f"<blockquote><b>Status: Metadata</b></blockquote>\n"
            f"<blockquote><b>Size: {size_str}</b></blockquote>\n"
            f"<blockquote><b>Engine: ffmpeg v4.4.2-0</b></blockquote>\n"
            f"<blockquote><b>User: {display_user} | ID: {user_id}</b></blockquote>",
            reply_markup=cancel_markup,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception:
        pass

    if batch_temp.CANCEL_TASKS.get(task_key, False):
        await _cleanup(temp_dir, file, smsg)
        raise ProcessCancelled("Cancelled before metadata")

    user_metadata = await db.get_metadata(user_id)
    file, _ = await add_metadata_with_ffmpeg(file, final_filename, user_metadata)

    # ── POST-METADATA cancel check ───────────────────────────────────────
    if batch_temp.CANCEL_TASKS.get(task_key, False):
        await _cleanup(temp_dir, file, smsg)
        raise ProcessCancelled("Cancelled after metadata")

    # ── Upload starting UI ────────────────────────────────────────────────
    try:
        await smsg.edit_text(
            f"<blockquote><b>{final_filename}</b></blockquote>\n"
            f"<blockquote><b>[□□□□□□□□□□□□] 0.0%</b></blockquote>\n"
            f"<blockquote><b>Processed: 0 B of {size_str}</b></blockquote>\n"
            f"<blockquote><b>Status: Upload | ETA: -</b></blockquote>\n"
            f"<blockquote><b>Speed: 0.0 B/s | Elapsed: 0s</b></blockquote>\n"
            f"<blockquote><b>Engine: PyroMulti v2.2.11</b></blockquote>\n"
            f"<blockquote><b>Mode:  #Leech | #Aria2</b></blockquote>\n"
            f"<blockquote><b>User: {display_user} | ID: {user_id}</b></blockquote>",
            reply_markup=cancel_markup,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception:
        pass

    # ── Thumbnail resolution (per-user custom thumbnail from DB, falling
    #    back to the original media's embedded thumbnail) ──────────────────
    ph_path = None

    thumb_id = await db.get_thumbnail(user_id)
    if thumb_id:
        try:
            ph_path = await client.download_media(
                thumb_id, file_name=f"{temp_dir}/custom_thumb.jpg"
            )
        except Exception as e:
            logger.error(f"Failed to download custom thumb: {e}")

    if not ph_path:
        try:
            if msg_type == "Video" and msg.video.thumbs:
                ph_path = await acc.download_media(
                    msg.video.thumbs[0].file_id, file_name=f"{temp_dir}/thumb.jpg"
                )
            elif msg_type == "Document" and msg.document.thumbs:
                ph_path = await acc.download_media(
                    msg.document.thumbs[0].file_id, file_name=f"{temp_dir}/thumb.jpg"
                )
        except Exception:
            pass

    # ── Caption ──────────────────────────────────────────────────────────
    custom_caption = await db.get_caption(user_id)
    if custom_caption:
        final_caption = custom_caption.format(
            filename=os.path.basename(file),
            size=humanbytes(file_size)
        )
    else:
        final_caption = script.CAPTION
        if msg.caption:
            final_caption += f"\n\n{msg.caption}"

    # ── UPLOAD ───────────────────────────────────────────────────────────
    upload_success = False
    sent_msg       = None
    start_time     = time.time()

    try:
        if batch_temp.CANCEL_TASKS.get(task_key, False):
            raise ProcessCancelled("Cancelled before upload")

        if msg_type == "Document":
            sent_msg = await client.send_document(
                message.chat.id, file,
                thumb=ph_path, caption=final_caption,
                file_name=os.path.basename(file),
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                progress=progress_callback,
                progress_args=(smsg, "upload", start_time, task_key, final_filename, display_user)
            )
            upload_success = True

        elif msg_type == "Video":
            sent_msg = await client.send_video(
                message.chat.id, file,
                duration=msg.video.duration,
                width=msg.video.width,
                height=msg.video.height,
                thumb=ph_path, caption=final_caption,
                file_name=os.path.basename(file),
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                progress=progress_callback,
                progress_args=(smsg, "upload", start_time, task_key, final_filename, display_user)
            )
            upload_success = True

        elif msg_type == "Audio":
            sent_msg = await client.send_audio(
                message.chat.id, file,
                thumb=ph_path, caption=final_caption,
                file_name=os.path.basename(file),
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                progress=progress_callback,
                progress_args=(smsg, "upload", start_time, task_key, final_filename, display_user)
            )
            upload_success = True

        elif msg_type == "Photo":
            sent_msg = await client.send_photo(
                message.chat.id, file,
                caption=final_caption,
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML
            )
            upload_success = True

    except ProcessCancelled:
        raise

    except asyncio.CancelledError:
        raise ProcessCancelled("Upload cancelled by user")

    except Exception as e:
        if ERROR_MESSAGE:
            await client.send_message(
                message.chat.id,
                f"Upload Failed: {e}",
                reply_to_message_id=message.id
            )

    # ── Forward to dump chat (this is what makes /setchat actually work) ──
    if upload_success:
        await _forward_to_dump_chat(client, user_id, sent_msg)

    # ── Cleanup ──────────────────────────────────────────────────────────
    if file and os.path.exists(file):
        try:
            os.remove(file)
        except Exception:
            pass

    if ph_path and os.path.exists(ph_path):
        try:
            os.remove(ph_path)
        except Exception:
            pass

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)

    try:
        await client.delete_messages(message.chat.id, [smsg.id])
    except Exception:
        pass

    return upload_success


# ===========================================================================
# Callback query handler
# ===========================================================================

@Client.on_callback_query()
async def button_callbacks(client: Client, callback_query: CallbackQuery):
    data    = callback_query.data
    message = callback_query.message
    if not message:
        return

    # cancel_ is handled by the dedicated handler above
    if data.startswith("cancel_"):
        return

    if data == "dev_info":
        await callback_query.answer(text=dev_text, show_alert=True)

    elif data == "channels_info":
        await callback_query.answer(text=channels_text, show_alert=True)

    elif data == "settings_btn":
        await settings_panel(client, callback_query)

    elif data == "buy_premium":
        buttons = [
            [InlineKeyboardButton("📸 Send Payment Proof", url="https://t.me/DmOwner")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="start_btn")]
        ]
        await client.edit_message_media(
            chat_id=message.chat.id,
            message_id=message.id,
            media=InputMediaPhoto(
                media=SUBSCRIPTION,
                caption=script.PREMIUM_TEXT.format(
                    callback_query.from_user.mention, UPI_ID, QR_CODE
                )
            ),
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data == "help_btn":
        buttons = [[InlineKeyboardButton("⬅️ Back to Home", callback_data="start_btn")]]
        await client.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.id,
            caption=script.HELP_TXT,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.HTML
        )

    elif data == "about_btn":
        buttons = [[InlineKeyboardButton("⬅️ Back to Home", callback_data="start_btn")]]
        await client.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.id,
            caption=script.ABOUT_TXT,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.HTML
        )

    elif data == "start_btn":
        bot  = await client.get_me()
        apis = ["https://api.waifu.pics/sfw/waifu", "https://nekos.life/api/v2/img/waifu"]
        try:
            response  = requests.get(random.choice(apis))
            response.raise_for_status()
            photo_url = response.json()["url"]
        except Exception as e:
            logger.error(f"Failed to fetch image from API: {e}")
            photo_url = "https://i.postimg.cc/cC7txyhz/15.png"

        buttons = [
            [
                InlineKeyboardButton("💎 Buy Premium", callback_data="buy_premium"),
                InlineKeyboardButton("🆘 Help & Guide", callback_data="help_btn")
            ],
            [
                InlineKeyboardButton("⚙️ Settings Panel", callback_data="settings_btn"),
                InlineKeyboardButton("ℹ️ About Bot",       callback_data="about_btn")
            ],
            [
                InlineKeyboardButton('📢 Channels',    callback_data="channels_info"),
                InlineKeyboardButton('👨‍💻 Developers', callback_data="dev_info")
            ]
        ]
        await client.edit_message_media(
            chat_id=message.chat.id,
            message_id=message.id,
            media=InputMediaPhoto(
                media=photo_url,
                caption=script.START_TXT.format(
                    callback_query.from_user.mention, bot.username, bot.first_name
                )
            ),
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data == "close_btn":
        await message.delete()

    elif data in ["cmd_list_btn", "user_stats_btn", "dump_chat_btn", "thumb_btn", "caption_btn"]:
        pass   # handled by the dedicated handler in cantarella/settings.py

    elif data == "prefsuf_info_btn":
        await callback_query.answer(
            "Use /prefix <text> and /suffix <text> in chat to manage these (or /settings → Prefix / Suffix).",
            show_alert=True
        )

    elif data == "metadata_info_btn":
        await callback_query.answer(
            "Use /metadata in chat to open the full metadata editor.",
            show_alert=True
        )

    await callback_query.answer()
