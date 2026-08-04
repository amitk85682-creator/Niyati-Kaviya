"""
╔══════════════════════════════════════════════════════╗
║              BOT BUILDER                              ║
║   Creates & configures bot instances                  ║
║   Supports multiple bots (Niyati, Palak, etc.)        ║
╚══════════════════════════════════════════════════════╝
"""

import json
import asyncio
from datetime import datetime

import pytz
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    filters,
)
from telegram.constants import ParseMode

from config import Config, logger
from database import db
from ai_engine import get_ai_engine
from health import health_server

from handlers import (
    start_command,
    help_command,
    about_command,
    mood_command,
    forget_command,
    meme_command,
    shayari_command,
    user_stats_command,
    handle_message,
    admin_stats_command,
    users_command,
    broadcast_command,
    adminhelp_command,
    grouphelp_command,
    groupinfo_command,
    setgeeta_command,
    setwelcome_command,
    groupstats_command,
    groupsettings_command,
    handle_new_member,
    handle_my_chat_member,
)


# ============================================================================
# SCHEDULED JOBS
# ============================================================================

async def send_daily_geeta(context):
    """Send daily Geeta quote to all groups"""
    bot_name = context.bot_data.get('bot_name', 'niyati')
    engine = get_ai_engine(bot_name)
    groups = await db.get_all_groups()
    quote = await engine.generate_geeta_quote()

    sent = 0
    for group in groups:
        chat_id = group.get('chat_id')
        settings = group.get('settings', {})
        if isinstance(settings, str):
            try:
                settings = json.loads(settings)
            except:
                settings = {}

        if not settings.get('geeta_enabled', True):
            continue

        try:
            await context.bot.send_message(
                chat_id=chat_id, text=quote,
                parse_mode=ParseMode.HTML
            )
            sent += 1
            await asyncio.sleep(0.1)
        except:
            pass

    logger.info(f"Daily Geeta sent to {sent} groups ({bot_name})")


async def cleanup_job(context):
    """Periodic cleanup"""
    from utils import rate_limiter
    await rate_limiter.cleanup_cooldowns()
    await db.cleanup_local_cache()
    logger.info("Cleanup completed")


# ============================================================================
# ERROR HANDLER
# ============================================================================

async def error_handler(update, context):
    """Handle errors"""
    logger.error(f"Error: {context.error}", exc_info=True)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "oops technical issue 😅 retry karo?"
            )
        except:
            pass


# ============================================================================
# BOT BUILDER
# ============================================================================

def setup_handlers(app: Application):
    """Register all handlers"""
    # Private commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("meme", meme_command))
    app.add_handler(CommandHandler("shayari", shayari_command))
    app.add_handler(CommandHandler("stats", user_stats_command))

    # Group commands
    app.add_handler(CommandHandler("grouphelp", grouphelp_command))
    app.add_handler(CommandHandler("groupinfo", groupinfo_command))
    app.add_handler(CommandHandler("setgeeta", setgeeta_command))
    app.add_handler(CommandHandler("setwelcome", setwelcome_command))
    app.add_handler(CommandHandler("groupstats", groupstats_command))
    app.add_handler(CommandHandler("groupsettings", groupsettings_command))

    # Admin commands
    app.add_handler(CommandHandler("adminstats", admin_stats_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("adminhelp", adminhelp_command))

    # New member welcome
    app.add_handler(ChatMemberHandler(
        handle_new_member, ChatMemberHandler.CHAT_MEMBER
    ))
    
    # Bot presence detection
    app.add_handler(ChatMemberHandler(
        handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER
    ))

    # Main message handler
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message
    ))

    # Error handler
    app.add_error_handler(error_handler)


def create_bot(bot_name: str, token: str, bot_username: str) -> Application:
    """
    Create a fully configured bot Application.

    Args:
        bot_name: 'niyati' or 'palak' (always lowercase)
        token: Telegram bot token
        bot_username: Bot's @username

    Returns:
        Configured Application ready to run
    """
    app = Application.builder().token(token).build()

    # Store bot identity in bot_data so handlers know which bot they serve
    app.bot_data['bot_name'] = bot_name
    app.bot_data['bot_username'] = bot_username

    # Register handlers
    setup_handlers(app)

    logger.info(f"Bot '{bot_name}' created with username @{bot_username}")
    return app


async def setup_jobs(app: Application, bot_name: str):
    """Setup scheduled jobs for a bot"""
    job_queue = app.job_queue
    if not job_queue:
        logger.warning(f"JobQueue not available for {bot_name}")
        return

    ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
    daily_time = datetime.now(ist).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    job_queue.run_daily(
        send_daily_geeta,
        time=daily_time.time(),
        days=(0, 1, 2, 3, 4, 5, 6),
        name=f"daily_geeta_{bot_name}",
    )

    # Cleanup every hour
    job_queue.run_repeating(
        cleanup_job,
        interval=Config.CACHE_CLEANUP_INTERVAL,
        first=60,
        name=f"cleanup_{bot_name}",
    )

    logger.info(f"Jobs scheduled for {bot_name}")
