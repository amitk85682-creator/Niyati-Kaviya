"""
╔══════════════════════════════════════════════════════╗
║           MAIN MESSAGE HANDLER                        ║
║   Private + Group with Smart Detection                ║
║   🔴 FIXED: Memory isolation, User identity tracking  ║
╚══════════════════════════════════════════════════════╝
"""

import re
import random
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from config import Config, logger
from database import db
from ai_engine import ai_engine
from memory import get_memory
from media import (
    should_send_image, should_send_sticker,
    get_mood_image, get_context_sticker,
    detect_mood_from_text,
)
from utils import (
    rate_limiter,
    is_user_talking_to_others,
    send_multi_messages,
)


def _get_bot_name(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get bot_name from context.bot_data"""
    return context.bot_data.get('bot_name', 'niyati')


def _get_bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get bot username from context.bot_data"""
    return context.bot_data.get('bot_username', 'Niyati_personal_bot')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle all text messages.
    
    🔴 FIXED:
    1. Memory isolation - Each bot has its own memory per user
    2. Group context - Now includes user identity (who said what)
    3. Reply tracking - Bot knows who it's replying to
    """
    message = update.message
    if not message or not message.text:
        return

    user = update.effective_user
    chat = update.effective_chat
    user_message = message.text

    # Ignore commands
    if user_message.startswith('/'):
        return

    is_group = chat.type in ['group', 'supergroup']
    is_private = chat.type == 'private'
    bot_name = _get_bot_name(context)
    bot_username = _get_bot_username(context)
    bot_id = context.bot.id
    memory = get_memory(bot_name)

    # ════════════════════════════════════════════════════════════════════
    # 🔴 SMART REPLY/MENTION DETECTION (Groups only)
    # ════════════════════════════════════════════════════════════════════
    if is_group:
        if is_user_talking_to_others(message, bot_username, bot_id, bot_name):
            logger.debug(f"👥 Skipping - User {user.id} is talking to others ({bot_name})")
            return

    # ════════════════════════════════════════════════════════════════════
    # FORCE SUBSCRIBE LOGIC
    # ════════════════════════════════════════════════════════════════════
    if is_group and user.id not in Config.ADMIN_IDS:
        targets = await db.get_group_fsub_targets(chat.id)

        if targets:
            missing_channels = []

            for target in targets:
                t_id = target.get('target_chat_id')
                if not t_id:
                    continue

                try:
                    member = await context.bot.get_chat_member(chat_id=t_id, user_id=user.id)
                    if member.status in ['left', 'kicked', 'restricted']:
                        missing_channels.append(target)
                except:
                    pass

            if missing_channels:
                logger.info(f"🚫 Blocking User {user.id} - Not joined {len(missing_channels)} channels")

                try:
                    await message.delete()
                except:
                    pass

                keyboard = [[InlineKeyboardButton(f"Join Channel {i+1} 🚀", url=ch.get('target_link', ''))]
                           for i, ch in enumerate(missing_channels)]

                msg = await message.reply_text(
                    f"🚫 <b>Ruko {user.first_name}!</b>\n\n"
                    f"Message karne ke liye {len(missing_channels)} channels join karo.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

                await asyncio.sleep(15)
                try:
                    await msg.delete()
                except:
                    pass

                return

    # ════════════════════════════════════════════════════════════════════
    # ANTI-SPAM (Groups Only)
    # ════════════════════════════════════════════════════════════════════
    if is_group:
        spam_keywords = ['cp', 'child porn', 'videos price', 'job', 'profit', 'investment', 'crypto', 'bitcoin']
        if any(word in user_message.lower() for word in spam_keywords):
            logger.info(f"🗑️ Spam detected from {user.id} ({bot_name})")
            return

    # ════════════════════════════════════════════════════════════════════
    # RATE LIMITING
    # ════════════════════════════════════════════════════════════════════
    allowed, reason = rate_limiter.check(user.id)
    if not allowed:
        if reason == "minute" and is_private:
            await message.reply_text("thoda slow 😅 saans to lene do!")
        return

    # ════════════════════════════════════════════════════════════════════
    # GROUP RESPONSE DECISION
    # ════════════════════════════════════════════════════════════════════
    reply_to_user_name = None

    if is_group:
        # 🔴 FIX: Track ALL group messages with user identity
        memory.add_group_message(chat.id, user.first_name, user.id, user_message)

        should_respond = False
        bot_mention = f"@{bot_username}".lower()
        msg_lower = user_message.lower()

        # 1. Bot @mentioned
        if bot_mention in msg_lower:
            should_respond = True
            user_message = re.sub(rf'@{bot_username}', '', user_message, flags=re.IGNORECASE).strip()
            logger.info(f"👆 [{bot_name}] Mentioned by {user.first_name}")

        # 2. Bot name mentioned (e.g. "niyati", "kavya")
        elif bot_name.lower() in msg_lower:
            should_respond = True
            logger.info(f"👆 [{bot_name}] Name mentioned by {user.first_name}")

        # 3. Reply to bot's message
        elif message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == bot_id:
                should_respond = True
                reply_to_user_name = user.first_name
                logger.info(f"↩️ [{bot_name}] Reply from {user.first_name}")

        # 4. Random response (low chance)
        if not should_respond:
            if random.random() < Config.GROUP_RESPONSE_RATE:
                should_respond = True
                logger.info(f"🎲 [{bot_name}] Random reply to {user.first_name}")
            else:
                return

        await db.get_or_create_group(bot_name, chat.id, chat.title)

    if is_private:
        await db.get_or_create_user(bot_name, user.id, user.first_name, user.username)
        await db.log_user_activity(user.id, "private_message")

    # ════════════════════════════════════════════════════════════════════
    # AI RESPONSE (Bot-Aware)
    # ════════════════════════════════════════════════════════════════════
    try:
        try:
            await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
        except:
            pass

        logger.info(f"💬 [{bot_name}] Processing: user={user.id} ({user.first_name}), "
                     f"msg='{user_message[:50]}...', {'group' if is_group else 'private'}")

        # 🔴 FIX: generate_response now uses bot_name for character & memory
        responses = await ai_engine.generate_response(
            bot_name=bot_name,
            user_id=user.id,
            chat_id=chat.id,
            user_message=user_message,
            user_name=user.first_name,
            is_group=is_group,
            reply_to_user=reply_to_user_name
        )

        logger.info(f"📤 [{bot_name}] Got {len(responses)} responses for user {user.id}")

        # Random Bonus (Private only)
        if is_private and random.random() < 0.1:
            prefs = await db.get_user_preferences(bot_name, user.id)
            bonus = await ai_engine.get_random_bonus()

            if bonus:
                is_shayari = "shayari" in str(bonus).lower() or "\n" in str(bonus)
                if is_shayari and not prefs.get('shayari_enabled', True):
                    bonus = None
                elif not is_shayari and not prefs.get('meme_enabled', True):
                    bonus = None

                if bonus:
                    responses.append(bonus)

        if responses:
            await send_multi_messages(
                context.bot,
                chat.id,
                responses,
                reply_to=message.message_id if is_group else None,
            )
            logger.info(f"✅ [{bot_name}] Sent {len(responses)} msgs to {user.id}")

            # ── MOOD IMAGE (very rare, private only) ──
            if is_private and should_send_image():
                detected_mood = detect_mood_from_text(user_message)
                img_url = get_mood_image(bot_name, detected_mood)
                if img_url:
                    try:
                        await context.bot.send_photo(
                            chat_id=chat.id, photo=img_url,
                        )
                        logger.info(f"🖼️ [{bot_name}] Sent mood image ({detected_mood}) to {user.id}")
                    except Exception as e:
                        logger.debug(f"Image send failed: {e}")

            # ── STICKER (occasional, based on conversation) ──
            if should_send_sticker():
                sticker_id = get_context_sticker(bot_name, user_message)
                if sticker_id:
                    try:
                        await context.bot.send_sticker(
                            chat_id=chat.id, sticker=sticker_id,
                        )
                        logger.info(f"🎭 [{bot_name}] Sent sticker to {user.id}")
                    except Exception as e:
                        logger.debug(f"Sticker send failed: {e}")

        else:
            logger.warning(f"⚠️ [{bot_name}] No responses generated for user {user.id}")

    except Exception as e:
        logger.error(f"❌ Message handling error ({bot_name}): {e}", exc_info=True)
        try:
            await message.reply_text("oops kuch gadbad... retry karo? 🫶")
        except:
            pass
