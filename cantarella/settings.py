import html
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import RPCError
from database.db import db
from cantarella.strings import COMMANDS_TXT
from cantarella.additional import METADATA_FIELDS
from logger import LOGGER

logger = LOGGER(__name__)

METADATA_LABELS = {
    "METADATA_TITLE":          "📄 Title",
    "METADATA_AUTHOR":         "✍️ Author",
    "METADATA_ARTIST":         "🎤 Artist",
    "METADATA_DESCRIPTION":    "📝 Description",
    "METADATA_COMMENT":        "💬 Comment",
    "METADATA_VIDEO_TITLE":    "🎬 Video Stream Title",
    "METADATA_AUDIO_TITLE":    "🎧 Audio Stream Title",
    "METADATA_SUBTITLE_TITLE": "💭 Subtitle Stream Title",
}


def main_settings_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Commands List", callback_data="cmd_list_btn")],
        [InlineKeyboardButton("📊 My Usage Stats", callback_data="user_stats_btn")],
        [InlineKeyboardButton("🗑 Dump Chat", callback_data="dump_chat_btn")],
        [
            InlineKeyboardButton("🖼 Thumbnail", callback_data="thumb_btn"),
            InlineKeyboardButton("📝 Caption", callback_data="caption_btn")
        ],
        [
            InlineKeyboardButton("🏷 Prefix / Suffix", callback_data="prefsuf_btn"),
            InlineKeyboardButton("🎬 Metadata", callback_data="metadata_btn")
        ],
        [InlineKeyboardButton("❌ Close Menu", callback_data="close_btn")]
    ])


def _truncate(value, length=18):
    if not value:
        return ""
    value = str(value)
    return value if len(value) <= length else value[:length - 1] + "…"


async def metadata_panel_buttons(user_id):
    current_meta = await db.get_metadata(user_id)
    rows = []
    for field in METADATA_FIELDS:
        label = METADATA_LABELS[field]
        value = current_meta.get(field)
        btn_text = f"{label}: {_truncate(value)}" if value else f"{label} (Not set)"
        rows.append([InlineKeyboardButton(btn_text, callback_data=f"meta_{field}")])
        if value:
            rows.append([InlineKeyboardButton(f"🗑 Delete {label}", callback_data=f"metadel_{field}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="settings_back_btn"),
                 InlineKeyboardButton("❌ Close", callback_data="close_btn")])
    return InlineKeyboardMarkup(rows)


def prefsuf_panel_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷 Set Prefix", callback_data="set_prefix_btn"),
         InlineKeyboardButton("🏷 Set Suffix", callback_data="set_suffix_btn")],
        [InlineKeyboardButton("🗑 Clear Prefix", callback_data="clear_prefix_btn"),
         InlineKeyboardButton("🗑 Clear Suffix", callback_data="clear_suffix_btn")],
        [InlineKeyboardButton("⬅️ Back", callback_data="settings_back_btn"),
         InlineKeyboardButton("❌ Close", callback_data="close_btn")]
    ])


async def safe_edit(callback_query: CallbackQuery, text, reply_markup):
    try:
        if callback_query.message.photo:
            await callback_query.edit_message_caption(
                caption=text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML
            )
        else:
            await callback_query.edit_message_text(
                text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True
            )
    except Exception:
        await callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)


async def edit_prompt_message(client: Client, chat_id, message_id, text, reply_markup):
    """Edit a previously-sent prompt message by chat_id/message_id. Falls back
    to caption-edit (photo messages) and finally to a brand new message if the
    original can no longer be edited, so the user always gets a visible reply."""
    try:
        await client.edit_message_text(
            chat_id, message_id, text, reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True
        )
        return
    except Exception as e:
        logger.info(f"edit_prompt_message: text edit failed ({e}), trying caption edit")
    try:
        await client.edit_message_caption(
            chat_id, message_id, caption=text, reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return
    except Exception as e:
        logger.info(f"edit_prompt_message: caption edit failed ({e}), sending fresh message")
    await client.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)


def metadata_field_text(field, value, status=None):
    label = METADATA_LABELS.get(field, field)
    safe_value = html.escape(value) if value else "Not set (original metadata preserved)"
    status_part = f" {status}" if status else ""
    return (
        f"<b>{label}</b>\n\n"
        f"<b>Current value:</b> <code>{safe_value}</code>{status_part}\n\n"
        f"<i>Send the new value as a text message.</i>\n"
        f"<i>Send <code>{{file_name}}</code> to use the saved filename automatically.</i>\n"
        f"<i>Send <code>clear</code> to remove this field.</i>"
    )


def metadata_field_buttons(field):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Delete This Field", callback_data=f"metadel_{field}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="metadata_btn"),
         InlineKeyboardButton("❌ Close", callback_data="close_btn")]
    ])


# ======================================================
# /settings - Enhanced Professional Settings Menu
# ======================================================
@Client.on_message(filters.command("settings") & filters.private)
async def settings_menu(client: Client, message: Message):
    user_id = message.from_user.id
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)
    is_premium = await db.check_premium(user_id)
    premium_badge = "💎 Premium Member" if is_premium else "👤 Free User"
    text = (
        f"<b>⚙️ Settings Panel</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Account:</b> {premium_badge}\n"
        f"<b>User ID:</b> <code>{user_id}</code>\n\n"
        f"<i>Select an option below to customize your experience.</i>"
    )
    await message.reply_text(text, reply_markup=main_settings_buttons(), parse_mode=enums.ParseMode.HTML)


# ======================================================
# /commands - Direct Access to Commands List
# ======================================================
@Client.on_message(filters.command("commands") & filters.private)
async def direct_commands(client: Client, message: Message):
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Open Settings", callback_data="settings_back_btn"), InlineKeyboardButton("❌ Close", callback_data="close_btn")]
    ])
    await message.reply_text(
        COMMANDS_TXT,
        reply_markup=buttons,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )


# ======================================================
# /setchat - Set or Clear Dump Chat
# ======================================================
@Client.on_message(filters.command("setchat") & filters.private)
async def set_dump_chat(client: Client, message: Message):
    user_id = message.from_user.id
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>🗑 Set Dump Chat</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/setchat &lt;chat_id&gt;</code> → Set forward destination\n"
            "<code>/setchat clear</code> → Remove dump chat\n\n"
            "<i>Example: /setchat -1001234567890</i>\n\n"
            "<b>Note:</b> The bot must be an admin/member of the target chat "
            "with permission to post messages, or saving will fail.",
            parse_mode=enums.ParseMode.HTML
        )
    arg = message.command[1].strip().lower()
    if arg == "clear":
        await db.set_dump_chat(user_id, None)
        return await message.reply_text("✅ <b>Dump Chat Cleared Successfully</b>", parse_mode=enums.ParseMode.HTML)
    try:
        chat_id = int(message.command[1].strip())
    except ValueError:
        return await message.reply_text(
            "❌ <b>Invalid Chat ID</b>\n\n<i>Must be a number (e.g., -1001234567890)</i>",
            parse_mode=enums.ParseMode.HTML
        )

    try:
        chat = await client.get_chat(chat_id)
        chat_title = chat.title or "Private Chat"
    except RPCError as e:
        return await message.reply_text(
            f"❌ <b>Unable to Access Chat</b>\n\n"
            f"<code>{html.escape(str(e))}</code>\n\n"
            f"<i>Make sure the bot has been added to that chat as a member/admin "
            f"and the chat ID is correct (forward a message from it, or use "
            f"@username_to_id_bot to confirm).</i>",
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        return await message.reply_text(f"❌ <b>Unable to Access Chat</b>\n<i>{html.escape(str(e))}</i>", parse_mode=enums.ParseMode.HTML)

    try:
        await client.send_message(chat_id, "✅ This chat is now set as your dump/forward destination.")
    except RPCError as e:
        return await message.reply_text(
            f"❌ <b>Bot Cannot Post In That Chat</b>\n\n"
            f"<code>{html.escape(str(e))}</code>\n\n"
            f"<i>Add the bot as an admin with \"Post Messages\" permission, then try again.</i>",
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        return await message.reply_text(f"❌ <b>Bot Cannot Post In That Chat</b>\n<i>{html.escape(str(e))}</i>", parse_mode=enums.ParseMode.HTML)

    await db.set_dump_chat(user_id, chat_id)
    await message.reply_text(
        f"✅ <b>Dump Chat Set Successfully</b>\n\n"
        f"<b>Forward To:</b> <code>{chat_id}</code>\n"
        f"<b>Title:</b> {html.escape(chat_title)}\n\n"
        f"<i>All future saved files will also be copied there automatically.</i>",
        parse_mode=enums.ParseMode.HTML
    )


# ======================================================
# /prefix (alias /preffix) and /suffix
# ======================================================
@Client.on_message(filters.command(["prefix", "preffix"]) & filters.private)
async def set_prefix_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)

    if len(message.command) < 2:
        current = await db.get_prefix(user_id)
        await db.set_pending_input(user_id, {"type": "prefix", "field": None})
        return await message.reply_text(
            f"<b>🏷 Set File Prefix</b>\n\n"
            f"<b>Current:</b> <code>{html.escape(current) if current else 'Not set'}</code>\n\n"
            f"<i>Send the new prefix as a text message, or send "
            f"<code>clear</code> to remove it.</i>\n\n"
            f"<i>Tip: you can also do this in one step with "
            f"<code>/prefix YourText</code> or <code>/prefix clear</code>.</i>",
            parse_mode=enums.ParseMode.HTML
        )

    value = message.text.split(None, 1)[1].strip()
    if value.lower() == "clear":
        await db.set_prefix(user_id, None)
        return await message.reply_text("✅ <b>Prefix Cleared.</b>", parse_mode=enums.ParseMode.HTML)

    await db.set_prefix(user_id, value)
    await db.clear_pending_input(user_id)
    await message.reply_text(f"✅ <b>Prefix Set:</b> <code>{html.escape(value)}</code>", parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("suffix") & filters.private)
async def set_suffix_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)

    if len(message.command) < 2:
        current = await db.get_suffix(user_id)
        await db.set_pending_input(user_id, {"type": "suffix", "field": None})
        return await message.reply_text(
            f"<b>🏷 Set File Suffix</b>\n\n"
            f"<b>Current:</b> <code>{html.escape(current) if current else 'Not set'}</code>\n\n"
            f"<i>Send the new suffix as a text message, or send "
            f"<code>clear</code> to remove it.</i>\n\n"
            f"<i>Tip: you can also do this in one step with "
            f"<code>/suffix YourText</code> or <code>/suffix clear</code>.</i>",
            parse_mode=enums.ParseMode.HTML
        )

    value = message.text.split(None, 1)[1].strip()
    if value.lower() == "clear":
        await db.set_suffix(user_id, None)
        return await message.reply_text("✅ <b>Suffix Cleared.</b>", parse_mode=enums.ParseMode.HTML)

    await db.set_suffix(user_id, value)
    await db.clear_pending_input(user_id)
    await message.reply_text(f"✅ <b>Suffix Set:</b> <code>{html.escape(value)}</code>", parse_mode=enums.ParseMode.HTML)


# ======================================================
# /metadata - Open the metadata settings panel
# ======================================================
@Client.on_message(filters.command("metadata") & filters.private)
async def metadata_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id, message.from_user.first_name)

    text = (
        "<b>🎬 Metadata Settings</b>\n\n"
        "<i>Tap a field below to view/edit it, or tap 🗑 to delete it instantly. "
        "These values are embedded into your saved video/audio files via ffmpeg.</i>\n\n"
        "<i>Tip: send <code>{file_name}</code> (literally) as the value for "
        "any field to automatically use the saved file's name there - this "
        "is commonly used for the Title field.</i>"
    )
    await message.reply_text(text, reply_markup=await metadata_panel_buttons(user_id), parse_mode=enums.ParseMode.HTML)


# ======================================================
# Pending text input handler — catches the next text message from a user
# who tapped a metadata/prefix/suffix button (or used the bare command).
# Registered in group=-1 so it runs BEFORE the generic link-saving handler
# in start.py (which must be set to group=1 — see note at bottom).
#
# FIX (root cause of "no response"): pending state used to live in an
# in-memory Python dict, which Koyeb's free tier wipes on every
# idle-restart/cold-start. It's now read from/written to MongoDB via
# db.get_pending_input / db.set_pending_input / db.clear_pending_input,
# so it survives restarts. Logging added at every branch so any future
# failure shows up in your Koyeb logs instead of as silence.
# ======================================================
@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"), group=-1)
async def capture_pending_input(client: Client, message: Message):
    user_id = message.from_user.id
    pending = await db.get_pending_input(user_id)
    logger.info(f"capture_pending_input: user={user_id} pending={pending}")
    if not pending:
        return  # nothing pending, let other handlers process this message normally

    value = message.text.strip()

    try:
        if pending["type"] == "metadata":
            field = pending["field"]
            prompt_chat_id = pending.get("chat_id")
            prompt_message_id = pending.get("message_id")

            if value.lower() == "clear":
                await db.set_metadata_field(user_id, field, None)
                new_text = metadata_field_text(field, None, status="Cleared ✅️")
            else:
                await db.set_metadata_field(user_id, field, value)
                new_text = metadata_field_text(field, value, status="Set successfully ✅️")

            logger.info(f"capture_pending_input: metadata field={field} saved for user={user_id}")

            if prompt_chat_id and prompt_message_id:
                await edit_prompt_message(
                    client, prompt_chat_id, prompt_message_id, new_text, metadata_field_buttons(field)
                )
            else:
                await message.reply_text(new_text, reply_markup=metadata_field_buttons(field), parse_mode=enums.ParseMode.HTML)

        elif pending["type"] == "prefix":
            if value.lower() == "clear":
                await db.set_prefix(user_id, None)
                await message.reply_text("✅ <b>Prefix Cleared.</b>", parse_mode=enums.ParseMode.HTML)
            else:
                await db.set_prefix(user_id, value)
                await message.reply_text(f"✅ <b>Prefix Set:</b> <code>{html.escape(value)}</code>", parse_mode=enums.ParseMode.HTML)

        elif pending["type"] == "suffix":
            if value.lower() == "clear":
                await db.set_suffix(user_id, None)
                await message.reply_text("✅ <b>Suffix Cleared.</b>", parse_mode=enums.ParseMode.HTML)
            else:
                await db.set_suffix(user_id, value)
                await message.reply_text(f"✅ <b>Suffix Set:</b> <code>{html.escape(value)}</code>", parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        logger.error(f"capture_pending_input: FAILED for user={user_id} pending={pending}: {e}")
        try:
            await message.reply_text(
                f"❌ <b>Something went wrong saving that value.</b>\n<code>{html.escape(str(e))}</code>",
                parse_mode=enums.ParseMode.HTML
            )
        except Exception:
            pass

    await db.clear_pending_input(user_id)
    message.stop_propagation()


# ======================================================
# Callbacks - Full Settings Navigation
# Pinned to group=-1 so it always runs before start.py's catch-all
# (which must be group=1 — see note below).
# ======================================================
@Client.on_callback_query(filters.regex(
    "^(cmd_list_btn|dump_chat_btn|thumb_btn|caption_btn|user_stats_btn|settings_back_btn|close_btn|"
    "prefsuf_btn|metadata_btn|set_prefix_btn|set_suffix_btn|clear_prefix_btn|clear_suffix_btn|"
    "meta_METADATA_TITLE|meta_METADATA_AUTHOR|meta_METADATA_ARTIST|meta_METADATA_DESCRIPTION|"
    "meta_METADATA_COMMENT|meta_METADATA_VIDEO_TITLE|meta_METADATA_AUDIO_TITLE|meta_METADATA_SUBTITLE_TITLE|"
    "metadel_METADATA_TITLE|metadel_METADATA_AUTHOR|metadel_METADATA_ARTIST|metadel_METADATA_DESCRIPTION|"
    "metadel_METADATA_COMMENT|metadel_METADATA_VIDEO_TITLE|metadel_METADATA_AUDIO_TITLE|metadel_METADATA_SUBTITLE_TITLE)$"
), group=-1)
async def settings_callbacks(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    logger.info(f"settings_callbacks: user={user_id} data={data}")

    back_close = [[InlineKeyboardButton("⬅️ Back", callback_data="settings_back_btn"), InlineKeyboardButton("❌ Close", callback_data="close_btn")]]

    if data == "cmd_list_btn":
        await safe_edit(callback_query, COMMANDS_TXT, InlineKeyboardMarkup(back_close))

    elif data == "dump_chat_btn":
        current = await db.get_dump_chat(user_id)
        if current:
            try:
                chat = await client.get_chat(current)
                title = chat.title or "Private Chat"
            except Exception:
                title = "Unknown (Inaccessible)"
            text = (
                f"<b>🗑 Current Dump Chat</b>\n\n"
                f"<b>Chat ID:</b> <code>{current}</code>\n"
                f"<b>Title:</b> {html.escape(title)}\n\n"
                "<i>All saved files are automatically forwarded here.</i>\n"
                "<i>Use /setchat &lt;chat_id&gt; to change, or /setchat clear to remove.</i>"
            )
        else:
            text = (
                "<b>🗑 No Dump Chat Set</b>\n\n"
                "<i>Saved files appear only in this chat.</i>\n"
                "<i>Use /setchat &lt;chat_id&gt; to enable forwarding "
                "(the bot must be added to that chat first).</i>"
            )
        await safe_edit(callback_query, text, InlineKeyboardMarkup(back_close))

    elif data == "thumb_btn":
        thumb = await db.get_thumbnail(user_id)
        if thumb:
            try:
                await callback_query.message.reply_photo(
                    thumb,
                    caption="<b>🖼 Your Current Custom Thumbnail</b>\n\n<i>Reply to a new photo with /set_thumb to update • /del_thumb to remove</i>",
                    parse_mode=enums.ParseMode.HTML
                )
                await callback_query.answer("Thumbnail preview sent below 👇")
            except Exception:
                await callback_query.answer("Could not load thumbnail preview.", show_alert=True)
        else:
            await safe_edit(
                callback_query,
                "<b>🖼 No Custom Thumbnail Set</b>\n\n"
                "<i>Reply to a photo with /set_thumb to set it as your default thumbnail for uploads.</i>",
                InlineKeyboardMarkup(back_close)
            )

    elif data == "caption_btn":
        caption = await db.get_caption(user_id)
        if caption:
            preview = caption.format(filename="Video_File_2024.mp4", size="1.2 GB")
            text = (
                f"<b>📝 Current Custom Caption</b>\n\n"
                f"<code>{html.escape(caption)}</code>\n\n"
                f"<b>Preview:</b>\n{html.escape(preview)}\n\n"
                "<i>Placeholders: {filename}, {size}</i>\n"
                "<i>/set_caption &lt;text&gt; to change • /del_caption to remove</i>"
            )
        else:
            text = (
                "<b>📝 No Custom Caption Set</b>\n\n"
                "<i>Use /set_caption &lt;text&gt; to set one.</i>\n"
                "<i>Supports {filename} and {size} placeholders.</i>"
            )
        await safe_edit(callback_query, text, InlineKeyboardMarkup(back_close))

    elif data == "prefsuf_btn":
        prefix = await db.get_prefix(user_id)
        suffix = await db.get_suffix(user_id)
        text = (
            f"<b>🏷 Prefix / Suffix Settings</b>\n\n"
            f"<b>Prefix:</b> <code>{html.escape(prefix) if prefix else 'Not set'}</code>\n"
            f"<b>Suffix:</b> <code>{html.escape(suffix) if suffix else 'Not set'}</code>\n\n"
            f"<i>These are applied to every filename you save.</i>"
        )
        await safe_edit(callback_query, text, prefsuf_panel_buttons())

    elif data == "set_prefix_btn":
        await db.set_pending_input(user_id, {"type": "prefix", "field": None})
        await safe_edit(
            callback_query,
            "<b>🏷 Send your new Prefix as a text message.</b>\n\n<i>Send 'clear' to remove it.</i>",
            InlineKeyboardMarkup(back_close)
        )

    elif data == "set_suffix_btn":
        await db.set_pending_input(user_id, {"type": "suffix", "field": None})
        await safe_edit(
            callback_query,
            "<b>🏷 Send your new Suffix as a text message.</b>\n\n<i>Send 'clear' to remove it.</i>",
            InlineKeyboardMarkup(back_close)
        )

    elif data == "clear_prefix_btn":
        await db.set_prefix(user_id, None)
        await callback_query.answer("Prefix cleared ✅", show_alert=True)

    elif data == "clear_suffix_btn":
        await db.set_suffix(user_id, None)
        await callback_query.answer("Suffix cleared ✅", show_alert=True)

    elif data == "metadata_btn":
        text = (
            "<b>🎬 Metadata Settings</b>\n\n"
            "<i>Tap a field to view/edit it, or tap 🗑 to delete it instantly.</i>\n\n"
            "<i>Tip: send <code>{file_name}</code> (literally) as the value to "
            "automatically use the saved file's name there.</i>"
        )
        await safe_edit(callback_query, text, await metadata_panel_buttons(user_id))

    elif data.startswith("metadel_"):
        field = data[len("metadel_"):]
        await db.set_metadata_field(user_id, field, None)
        await callback_query.answer(f"{METADATA_LABELS.get(field, field)} deleted ✅", show_alert=False)
        text = (
            "<b>🎬 Metadata Settings</b>\n\n"
            "<i>Tap a field to view/edit it, or tap 🗑 to delete it instantly.</i>\n\n"
            "<i>Tip: send <code>{file_name}</code> (literally) as the value to "
            "automatically use the saved file's name there.</i>"
        )
        await safe_edit(callback_query, text, await metadata_panel_buttons(user_id))

    elif data.startswith("meta_"):
        field = data[len("meta_"):]
        current = await db.get_metadata_field(user_id, field)
        text = metadata_field_text(field, current)
        await safe_edit(callback_query, text, metadata_field_buttons(field))

        prompt_msg = callback_query.message
        await db.set_pending_input(user_id, {
            "type": "metadata",
            "field": field,
            "chat_id": prompt_msg.chat.id,
            "message_id": prompt_msg.id,
        })
        logger.info(f"settings_callbacks: pending input set for user={user_id} field={field} msg={prompt_msg.id}")

    elif data == "user_stats_btn":
        is_premium = await db.check_premium(user_id)
        user_data = await db.col.find_one({'id': int(user_id)})

        if is_premium:
            limit_text = "♾️ Unlimited"
            usage_text = "Ignored (Premium)"
        else:
            daily_limit = 10
            used = user_data.get('daily_usage', 0) if user_data else 0
            limit_text = f"{daily_limit} Files / 24h"
            usage_text = f"{used} / {daily_limit}"
        text = (
            f"<b>📊 My Usage Statistics</b>\n\n"
            f"<b>Plan:</b> {'💎 Premium' if is_premium else '👤 Free'}\n"
            f"<b>Daily Limit:</b> <code>{limit_text}</code>\n"
            f"<b>Today's Usage:</b> <code>{usage_text}</code>\n\n"
            f"<i>Upgrade to Premium for unlimited downloads!</i>"
        )
        await safe_edit(callback_query, text, InlineKeyboardMarkup(back_close))

    elif data == "settings_back_btn":
        is_premium = await db.check_premium(user_id)
        premium_badge = "💎 Premium Member" if is_premium else "👤 Free User"
        text = (
            f"<b>⚙️ Settings Panel</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Account:</b> {premium_badge}\n"
            f"<b>User ID:</b> <code>{user_id}</code>\n\n"
            f"<i>Select an option below to customize your experience.</i>"
        )
        await safe_edit(callback_query, text, main_settings_buttons())

    elif data == "close_btn":
        await callback_query.message.delete()

    await callback_query.answer()
