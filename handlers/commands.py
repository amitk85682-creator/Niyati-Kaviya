"""
╔══════════════════════════════════════════════════════╗
║           COMMAND HANDLERS                            ║
║   /start, /help, /about, /mood, /forget, etc.         ║
╚══════════════════════════════════════════════════════╝
"""

import json
import random

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import Config, logger
from database import db
from characters import get_character
from utils import TimeAware, Mood, StylishFonts, send_multi_messages


def _get_bot_name(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get bot_name from context.bot_data"""
    return context.bot_data.get('bot_name', 'niyati')


# ============================================================================
# /start
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start"""
    user = update.effective_user
    chat = update.effective_chat
    is_private = chat.type == 'private'
    bot_name = _get_bot_name(context)
    character = get_character(bot_name)

    user_mention = StylishFonts.mention(user.first_name, user.id)

    if is_private:
        await db.get_or_create_user(bot_name, user.id, user.first_name, user.username)

        greeting = TimeAware.get_greeting()
        messages = [greeting]
        for msg in character['start_messages_private']:
            messages.append(msg.format(mention=user_mention))

        await send_multi_messages(context.bot, chat.id, messages, parse_mode=ParseMode.HTML)

    else:
        await db.get_or_create_group(bot_name, chat.id, chat.title)

        await update.message.reply_html(
            character['start_message_group'].format(mention=user_mention)
        )

    logger.info(f"Start ({bot_name}): {user.id} in {'private' if is_private else 'group'}")


# ============================================================================
# /help
# ============================================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help"""
    bot_name = _get_bot_name(context)
    character = get_character(bot_name)
    await update.message.reply_html(character['help_text'])


# ============================================================================
# /about
# ============================================================================

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about"""
    bot_name = _get_bot_name(context)
    character = get_character(bot_name)
    await update.message.reply_html(character['about_text'])


# ============================================================================
# /mood
# ============================================================================

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mood"""
    mood = Mood.get_random_mood()
    time_period = TimeAware.get_time_period()
    emoji = Mood.get_mood_emoji(mood)

    messages = [
        f"aaj ka mood? {emoji}",
        f"{mood.upper()} vibes hai yaar",
        f"waise {time_period} ho gayi... time flies!"
    ]

    await send_multi_messages(context.bot, update.effective_chat.id, messages)


# ============================================================================
# /forget
# ============================================================================

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forget"""
    user = update.effective_user
    bot_name = _get_bot_name(context)
    character = get_character(bot_name)

    await db.clear_user_memory(bot_name, user.id)

    await send_multi_messages(
        context.bot, update.effective_chat.id,
        character['forget_messages']
    )


# ============================================================================
# /meme on/off
# ============================================================================

async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle meme preference"""
    user = update.effective_user
    bot_name = _get_bot_name(context)
    args = context.args

    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /meme on ya /meme off")
        return

    value = args[0].lower() == 'on'
    await db.update_preference(bot_name, user.id, 'meme', value)

    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Memes: {status}")


# ============================================================================
# /shayari on/off
# ============================================================================

async def shayari_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle shayari preference"""
    user = update.effective_user
    bot_name = _get_bot_name(context)
    args = context.args

    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /shayari on ya /shayari off")
        return

    value = args[0].lower() == 'on'
    await db.update_preference(bot_name, user.id, 'shayari', value)

    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Shayari: {status}")


# ============================================================================
# /stats
# ============================================================================

async def user_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's personal stats"""
    user = update.effective_user
    bot_name = _get_bot_name(context)
    user_data = await db.get_or_create_user(bot_name, user.id, user.first_name, user.username)

    messages = user_data.get('messages', [])
    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except:
            messages = []

    prefs = user_data.get('preferences', {})
    if isinstance(prefs, str):
        try:
            prefs = json.loads(prefs)
        except:
            prefs = {}

    created_at = user_data.get('created_at', 'Unknown')[:10] if user_data.get('created_at') else 'Unknown'

    character = get_character(bot_name)

    stats_text = f"""
📊 <b>Your Stats ({character['name']})</b>

<b>User:</b> {user.first_name}
<b>ID:</b> <code>{user.id}</code>

<b>Conversation:</b>
• Messages: {len(messages)}
• Joined: {created_at}

<b>Preferences:</b>
• Memes: {'✅' if prefs.get('meme_enabled', True) else '❌'}
• Shayari: {'✅' if prefs.get('shayari_enabled', True) else '❌'}
"""
    await update.message.reply_html(stats_text)
