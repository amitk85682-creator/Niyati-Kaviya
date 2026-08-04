"""
╔══════════════════════════════════════════════════════╗
║           ADMIN COMMAND HANDLERS                      ║
║   /adminstats, /users, /broadcast, /adminhelp         ║
╚══════════════════════════════════════════════════════╝
"""

import html
import asyncio
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter

from config import Config, logger
from database import db
from utils import rate_limiter
from health import health_server


def _get_bot_name(context):
    return context.bot_data.get('bot_name', 'niyati')


async def admin_check(update):
    return update.effective_user.id in Config.ADMIN_IDS


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        await update.message.reply_text("Only admins!")
        return

    bot_name = _get_bot_name(context)
    uc = await db.get_user_count(bot_name)
    gc = await db.get_group_count()
    dr_niyati = rate_limiter.get_daily_total("niyati")
    dr_palak = rate_limiter.get_daily_total("palak")
    dr_total = rate_limiter.get_daily_total()
    
    up = datetime.now(timezone.utc) - health_server.start_time
    h = int(up.total_seconds() // 3600)
    m = int((up.total_seconds() % 3600) // 60)
    ds = "🟢 Connected" if db.connected else "🔴 Local"

    await update.message.reply_html(
        f"📊 <b>Stats ({bot_name.capitalize()})</b>\n\n"
        f"<b>Users:</b> {uc}\n<b>Groups:</b> {gc}\n"
        f"<b>Requests:</b> {dr_total} (N: {dr_niyati}, P: {dr_palak})\n<b>Uptime:</b> {h}h {m}m\n"
        f"<b>DB:</b> {ds}\n<b>Cache:</b> {len(db.local_users)}u / {len(db.local_groups)}g"
    )


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        await update.message.reply_text("Only admins!")
        return

    bot_name = _get_bot_name(context)
    users = await db.get_all_users(bot_name)
    lines = []
    for u in users[:20]:
        n = u.get('first_name', '?')
        uid = u.get('user_id', 0)
        un = u.get('username', '')
        l = f"• {n}"
        if un:
            l += f" (@{un})"
        l += f" - <code>{uid}</code>"
        lines.append(l)

    ul = "\n".join(lines) if lines else "No users"
    await update.message.reply_html(f"👥 <b>Users (20)</b>\n\n{ul}\n\n<b>Total:</b> {len(users)}")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return

    args = context.args
    if not args or args[0] != Config.BROADCAST_PIN:
        await update.message.reply_html("❌ <b>Wrong PIN!</b>\nUsage: /broadcast PIN Message")
        return

    msg_text = ' '.join(args[1:]) if len(args) > 1 else None
    reply_msg = update.message.reply_to_message

    if not msg_text and not reply_msg:
        await update.message.reply_text("❌ Message likho ya reply karo!")
        return

    status = await update.message.reply_text("📢 Starting...")
    bot_name = _get_bot_name(context)
    users = await db.get_all_users(bot_name)
    ok, fail, total = 0, 0, len(users)
    ft = html.escape(msg_text) if msg_text else None

    for i, u in enumerate(users):
        uid = u.get('user_id')
        if not uid:
            continue
        try:
            if reply_msg:
                await context.bot.copy_message(uid, update.effective_chat.id, reply_msg.message_id)
            else:
                await context.bot.send_message(uid, ft, parse_mode=ParseMode.HTML)
            ok += 1
        except Forbidden:
            fail += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            fail += 1
        except:
            fail += 1
        if i % 20 == 0:
            try:
                await status.edit_text(f"📢 {i}/{total} ✅{ok} ❌{fail}")
            except:
                pass
        await asyncio.sleep(0.05)

    await status.edit_text(
        f"✅ <b>Done!</b>\n👥 {total} | ✅ {ok} | ❌ {fail}",
        parse_mode=ParseMode.HTML
    )


async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        await update.message.reply_text("Only admins!")
        return
    await update.message.reply_html(
        "🔐 <b>Admin Commands</b>\n\n"
        "• /adminstats - Stats\n• /users - User list\n"
        "• /broadcast [PIN] [msg] - Broadcast\n• /adminhelp - This"
    )
