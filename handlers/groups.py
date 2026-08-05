"""
╔══════════════════════════════════════════════════════╗
║           GROUP COMMAND HANDLERS                      ║
║   /grouphelp, /groupinfo, /setgeeta, etc.             ║
╚══════════════════════════════════════════════════════╝
"""

import json

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatMemberStatus

from config import Config, logger
from database import db
from characters import get_character
from utils import StylishFonts, send_multi_messages


def _get_bot_name(context):
    return context.bot_data.get('bot_name', 'niyati')


async def is_group_admin(update, context):
    user = update.effective_user
    chat = update.effective_chat
    if user.id in Config.ADMIN_IDS:
        return True
    try:
        member = await chat.get_member(user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False


async def grouphelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return

    bot_name = _get_bot_name(context)
    character = get_character(bot_name)
    name = character['name']

    await update.message.reply_html(
        f"🌸 <b>{name} Group Commands</b> 🌸\n\n"
        f"<b>Everyone:</b>\n"
        f"• /grouphelp - Yeh menu\n• /groupinfo - Group info\n"
        f"• @{name}Bot [msg] - Mujhse baat karo\n• Reply to my msg\n\n"
        f"<b>Admin Only:</b>\n"
        f"• /setgeeta on/off - Daily Geeta\n• /setwelcome on/off - Welcome msg\n"
        f"• /groupstats - Stats\n• /groupsettings - Settings"
    )


async def groupinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return

    bot_name = _get_bot_name(context)
    group_data = await db.get_or_create_group(bot_name, chat.id, chat.title)

    settings = group_data.get('settings', {})
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except:
            settings = {}

    await update.message.reply_html(
        f"📊 <b>Group Info</b>\n\n"
        f"<b>Name:</b> {chat.title}\n<b>ID:</b> <code>{chat.id}</code>\n\n"
        f"<b>Settings:</b>\n"
        f"• Geeta: {'✅' if settings.get('geeta_enabled', True) else '❌'}\n"
        f"• Welcome: {'✅' if settings.get('welcome_enabled', True) else '❌'}"
    )


async def setgeeta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Only admins!")
        return

    args = context.args
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /setgeeta on ya /setgeeta off")
        return

    bot_name = _get_bot_name(context)
    value = args[0].lower() == 'on'
    await db.update_group_settings(bot_name, chat.id, 'geeta_enabled', value)
    await update.message.reply_text(f"Daily Geeta: {'ON ✅' if value else 'OFF ❌'}")


async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Only admins!")
        return

    args = context.args
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /setwelcome on ya /setwelcome off")
        return

    bot_name = _get_bot_name(context)
    value = args[0].lower() == 'on'
    await db.update_group_settings(bot_name, chat.id, 'welcome_enabled', value)
    await update.message.reply_text(f"Welcome: {'ON ✅' if value else 'OFF ❌'}")


async def groupstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Only admins!")
        return

    cached = len(db.get_group_context(chat.id))
    await update.message.reply_html(
        f"📊 <b>Group Stats</b>\n\n"
        f"<b>Group:</b> {chat.title}\n<b>Cached Msgs:</b> {cached}"
    )


async def groupsettings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Only admins!")
        return

    bot_name = _get_bot_name(context)
    group_data = await db.get_or_create_group(bot_name, chat.id, chat.title)
    settings = group_data.get('settings', {})
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except:
            settings = {}

    await update.message.reply_html(
        f"⚙️ <b>Group Settings</b>\n\n"
        f"<b>Group:</b> {chat.title}\n\n"
        f"• Geeta: {'✅ ON' if settings.get('geeta_enabled', True) else '❌ OFF'}\n"
        f"• Welcome: {'✅ ON' if settings.get('welcome_enabled', True) else '❌ OFF'}"
    )


async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining group"""
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return

    bot_name = _get_bot_name(context)
    character = get_character(bot_name)
    group_data = await db.get_or_create_group(bot_name, chat.id, chat.title)

    settings = group_data.get('settings', {})
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except:
            settings = {}

    if not settings.get('welcome_enabled', True):
        return

    if not update.message or not update.message.new_chat_members:
        return

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue

        mention = StylishFonts.mention(member.first_name, member.id)
        messages = [msg.format(mention=mention) for msg in character['welcome_messages']]

        await send_multi_messages(context.bot, chat.id, messages, parse_mode=ParseMode.HTML)
        await db.log_user_activity(member.id, f"joined_group:{chat.id}")
