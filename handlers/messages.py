"""
╔══════════════════════════════════════════════════════╗
║           MAIN MESSAGE HANDLER                        ║
║   Private + Group with Smart Detection                ║
║   Cross-bot awareness, Shared memory,                 ║
║   3 real people chatting feel                          ║
╚══════════════════════════════════════════════════════╝
"""

import re
import random
from typing import Optional
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from config import Config, logger
from database import db
from ai_engine import get_ai_engine
from memory import get_memory
from group_room import group_manager
from utils import (
    rate_limiter,
    is_user_talking_to_others,
    send_multi_messages,
)
from emotional_core import (
    state_manager, AppraisalEngine, EmotionEngine, 
    ConversationPolicy, DailyLifeGenerator, EmotionalInputContext
)
from datetime import datetime, timezone

# ════════════════════════════════════════════════════════════════════
# INLINE MEDIA SYSTEM (mood images + stickers)
# ════════════════════════════════════════════════════════════════════

_IMAGE_SEND_CHANCE = 0.03
_STICKER_SEND_CHANCE = 0.05

_MOOD_IMAGES = {
    'niyati': {
        'happy': [
            "https://i.pinimg.com/736x/54/5b/07/545b07562a654b0be845b5fa45e5a4d3.jpg",
            "https://i.pinimg.com/736x/e8/dc/f6/e8dcf6a3c1a7e4a6d8a7b5c3e1f2a4b6.jpg",
        ],
        'sad': ["https://i.pinimg.com/736x/e1/f2/a3/e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6.jpg"],
        'playful': ["https://i.pinimg.com/736x/a1/b2/c3/a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6.jpg"],
        'sleepy': ["https://i.pinimg.com/736x/a3/b4/c5/a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8.jpg"],
        'angry': [], 'love': []
    },
    'palak': {
        'happy': [
            "https://i.pinimg.com/736x/8c/3d/f1/8c3df1a2b4c5d6e7f8a9b0c1d2e3f4a5.jpg",
            "https://i.pinimg.com/736x/f2/a1/b3/f2a1b3c4d5e6f7a8b9c0d1e2f3a4b5c6.jpg",
        ],
        'sad': ["https://i.pinimg.com/736x/f3/a4/b5/f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8.jpg"],
        'playful': ["https://i.pinimg.com/736x/b3/c4/d5/b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8.jpg"],
        'sleepy': ["https://i.pinimg.com/736x/b5/c6/d7/b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0.jpg"],
        'angry': [], 'love': []
    }
}

_CONTEXT_STICKERS = {
    'niyati': {'haha': [], 'lol': [], 'sad': [], 'love': [], 'angry': [],
               'hi': [], 'bye': [], 'thanks': [], 'sorry': [], 'miss': []},
    'palak':  {'haha': [], 'lol': [], 'sad': [], 'love': [], 'angry': [],
               'hi': [], 'bye': [], 'thanks': [], 'sorry': [], 'miss': []},
}


def should_send_image():
    return random.random() < _IMAGE_SEND_CHANCE

def should_send_sticker():
    return random.random() < _STICKER_SEND_CHANCE

def get_mood_image(bot_name, mood):
    bot_imgs = _MOOD_IMAGES.get(bot_name, {})
    imgs = bot_imgs.get(mood, []) or bot_imgs.get('happy', [])
    return random.choice(imgs) if imgs else None

def get_context_sticker(bot_name, message_text):
    bot_stk = _CONTEXT_STICKERS.get(bot_name, {})
    ml = message_text.lower()
    for kw, ids in bot_stk.items():
        if kw in ml and ids:
            return random.choice(ids)
    return None

def detect_mood_from_text(text):
    tl = text.lower()
    if any(w in tl for w in ['sad','dukhi','rona','ro rha','miss','lonely','akela','hurt','pain','toot']):
        return 'sad'
    if any(w in tl for w in ['love','pyaar','dil','crush','romantic','valentine','jaanu','baby']):
        return 'love'
    if any(w in tl for w in ['angry','gussa','irritate','chid','pagal','stupid','hate']):
        return 'angry'
    if any(w in tl for w in ['neend','sona','sleep','tired','thak','lazy','bore']):
        return 'sleepy'
    if any(w in tl for w in ['happy','khush','mast','badhiya','amazing','awesome','wow','yay','party']):
        return 'happy'
    return 'happy'


# ════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════

def _get_bot_name(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get bot_name from context.bot_data"""
    return context.bot_data.get('bot_name', 'niyati')


def _get_bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get bot username from context.bot_data"""
    return context.bot_data.get('bot_username', 'Niyati_personal_bot')


def _resolve_reply_to_bot(message, bot_name: str) -> Optional[str]:
    """
    If the message is a reply-to a bot message, return the internal bot name
    of the replied-to bot. Returns None if not a reply or replied to a human.
    """
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return None
    replied_user = message.reply_to_message.from_user
    if not replied_user.is_bot:
        return None
    
    # Check by registered bot ID (primary)
    for name in ['niyati', 'palak']:
        registered_id = group_manager.get_bot_id(name)
        if registered_id and registered_id == replied_user.id:
            return name
    
    # Fallback: check by username
    replied_username = (replied_user.username or '').lower()
    if replied_username == Config.NIYATI_BOT_USERNAME.lower():
        return 'niyati'
    if replied_username == Config.PALAK_BOT_USERNAME.lower():
        return 'palak'
    
    return None


def _is_trusted_partner(user, bot_name: str) -> bool:
    """
    Check if the user is the trusted partner bot.
    Uses registered bot ID as primary check, username as secondary.
    Handles user.username being None safely.
    """
    partner_name = group_manager.get_partner_name(bot_name)
    if not partner_name:
        return False
    
    # Primary: check by registered Telegram user ID
    partner_id = group_manager.get_bot_id(partner_name)
    if partner_id and user.id == partner_id:
        return True
    
    # Secondary: check by username (may not be set)
    partner_username = Config.PALAK_BOT_USERNAME if partner_name == 'palak' else Config.NIYATI_BOT_USERNAME
    user_username = (user.username or '').lower()
    if partner_username and user_username == partner_username.lower():
        return True
    
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle all text messages.
    
    Cross-bot awareness:
    - Both Niyati and Palak participate in groups like 3 real people
    - Shared memory so they see each other's messages
    - Smart response logic: sometimes one responds, sometimes both
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
    engine = get_ai_engine(bot_name)

    # ════════════════════════════════════════════════════════════════════
    # PRESENCE CHECK
    # ════════════════════════════════════════════════════════════════════
    if is_group:
        await group_manager.update_presence(chat.id, bot_name, True)
        
        room = await group_manager.get_room(chat.id)
        if room.is_partner_present(bot_name) is None:
            partner_name = group_manager.get_partner_name(bot_name)
            if partner_name:
                partner_id = group_manager.get_bot_id(partner_name)
                if partner_id:
                    try:
                        member = await context.bot.get_chat_member(chat.id, partner_id)
                        is_present = member.status in ['member', 'administrator']
                    except Exception:
                        is_present = False
                    await group_manager.update_presence(chat.id, partner_name, is_present)

    # ════════════════════════════════════════════════════════════════════
    # BOT-TO-BOT SAFEGUARDS
    # ════════════════════════════════════════════════════════════════════
    if user.is_bot:
        if not is_group:
            return  # No bot-to-bot in private

        if user.id == bot_id:
            return  # Ignore our own messages

        if not _is_trusted_partner(user, bot_name):
            logger.debug(f"Ignoring unknown bot: {(user.username or 'no-username')}")
            return

        # Partner bot message must relate to a human trigger
        trigger_message_id = message.reply_to_message.message_id if message.reply_to_message else None

        # It's the partner bot! We log the message to transcript, but NEVER generate AI.
        await group_manager.process_partner_message(
            bot_name=bot_name,
            chat_id=chat.id,
            message_id=message.message_id,
            partner_id=user.id,
            partner_name=user.first_name,
            text=user_message,
            trigger_message_id=trigger_message_id
        )
        return

    else:
        # ════════════════════════════════════════════════════════════════════
        # SMART REPLY/MENTION DETECTION (Groups only)
        # ════════════════════════════════════════════════════════════════════
        if is_group:
            if is_user_talking_to_others(message, bot_username, bot_id, bot_name):
                logger.debug(f"Skipping - User {user.id} is talking to other humans ({bot_name})")
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
                    logger.info(f"Blocking User {user.id} - Not joined {len(missing_channels)} channels")
    
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
                logger.info(f"Spam detected from {user.id} ({bot_name})")
                return

        # ════════════════════════════════════════════════════════════════════
        # RATE LIMITING
        # ════════════════════════════════════════════════════════════════════
        allowed, reason = await rate_limiter.check(bot_name, user.id)
        if not allowed:
            if reason == "minute" and is_private:
                await message.reply_text("thoda slow 😅 saans to lene do!")
            return

        # ════════════════════════════════════════════════════════════════════
        # GROUP RESPONSE DECISION (Cross-Bot Aware)
        # ════════════════════════════════════════════════════════════════════
        reply_to_user_name = None
        chip_in_delay = 0

        if is_group:
            # Resolve reply-to bot for routing
            reply_to_bot = _resolve_reply_to_bot(message, bot_name)
            
            should_proceed, planned, trigger_message_id = await group_manager.process_human_message(
                bot_name=bot_name,
                chat_id=chat.id,
                message_id=message.message_id,
                sender_id=user.id,
                sender_name=user.first_name,
                text=user_message,
                reply_to_bot_name=reply_to_bot
            )
            if not should_proceed:
                return
                
            # Also save to DB for persistence
            db.add_group_message(chat.id, user.first_name, user.id, user_message)

            # COORDINATOR DECISION
            if bot_name not in planned:
                logger.debug(f"[{bot_name}] Not selected to respond to {user.first_name}")
                return
                
            await db.get_or_create_group(bot_name, chat.id, chat.title)
                
            # Wait for our turn if we are second
            await group_manager.wait_for_turn(bot_name, chat.id, planned, trigger_message_id)
            
            # Reserve before generating AI response
            reserved = await group_manager.reserve_bot(bot_name, chat.id, trigger_message_id)
            if not reserved:
                logger.debug(f"[{bot_name}] Could not reserve for trigger {trigger_message_id}, likely already inflight")
                return
            
            reply_to_user_name = None

        if is_private:
            await db.get_or_create_user(bot_name, user.id, user.first_name, user.username)
            await db.log_user_activity(user.id, "private_message")


    # ════════════════════════════════════════════════════════════════════
    # AI RESPONSE (Bot-Aware, Per-Bot Engine)
    # ════════════════════════════════════════════════════════════════════
    try:
        try:
            await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
        except:
            pass

        logger.info(f"[{bot_name}] Processing: user={user.id} ({user.first_name}), "
                     f"msg='{user_message[:50]}...', {'group' if is_group else 'private'}")

        # ════════════════════════════════════════════════════════════════════
        # EMOTIONAL CORE ORCHESTRATION
        # ════════════════════════════════════════════════════════════════════
        now = datetime.now(timezone.utc)
        state = await state_manager.get_state(bot_name, chat.id, user.id)
        prev_action = state.recent_actions[-1] if state.recent_actions else None
        
        reply_bot_name = _resolve_reply_to_bot(message, bot_name)
        
        input_context = EmotionalInputContext(
            bot_name=bot_name,
            chat_id=chat.id,
            user_id=user.id,
            message_id=message.message_id,
            text=user_message,
            is_group=is_group,
            replied_to_bot_name=reply_bot_name,
            semantic_target_bot=reply_bot_name if reply_bot_name else None,
            previous_character_action=prev_action
        )
        
        state_manager.apply_decay(state, now)
        
        date_str = now.strftime("%Y-%m-%d")
        if state.daily_life.date != date_str:
            state.daily_life = DailyLifeGenerator.generate(bot_name, date_str)
            
        appraisal = AppraisalEngine.appraise(input_context, state.relationship)
        EmotionEngine.apply_appraisal(state, appraisal, message.message_id)
        decision = ConversationPolicy.decide_action(state, appraisal, is_group)
        
        await state_manager.save_state(state)
        
        logger.info(f"[Emotion] bot={bot_name} user={user.id} intent={appraisal.intent} action={decision.action.name}")
        
        if not decision.should_respond:
            logger.info(f"[Policy] bot={bot_name} respond=False reason={decision.reason}")
            await state_manager.record_response_outcome(bot_name, chat.id, user.id, True, decision.action)
            if is_group and 'trigger_message_id' in locals():
                await group_manager.release_bot(bot_name, chat.id, trigger_message_id)
            return

        def label(val):
            if val < 0.33: return "low"
            if val < 0.66: return "medium"
            return "high"
            
        psych_context = (
            f"Current psychological state:\n"
            f"- energy: {label(state.mood.energy)}\n"
            f"- playfulness: {label(state.mood.playfulness)}\n"
            f"- irritation: {label(state.mood.irritation)}\n"
            f"- embarrassment: {label(state.mood.embarrassment)}\n"
            f"- relationship stage: {state.relationship.stage}\n"
            f"- trust: {label(state.relationship.trust)}\n"
            f"- message interpretation: {appraisal.intent}\n"
            f"- selected action: {decision.action.name}\n"
            f"- content goal: {decision.content_goal}\n"
            f"- current activity: {state.daily_life.current_activity} at {state.daily_life.location}\n"
            f"- active concern: {state.daily_life.active_concern}\n"
            f"- avoid mentioning: {'college, Bruno, painting' if bot_name == 'palak' else 'hobbies randomly'}\n"
            f"- maximum response length: {decision.max_sentences} sentence(s)\n"
            f"- emoji allowed: {'yes' if decision.allow_emoji else 'no'}\n"
        )

        responses = await engine.generate_response(
            bot_name=bot_name,
            user_id=user.id,
            chat_id=chat.id,
            user_message=user_message,
            user_name=user.first_name,
            is_group=is_group,
            reply_to_user=reply_to_user_name,
            psychological_context=psych_context
        )

        logger.info(f"[{bot_name}] Got {len(responses)} responses for user {user.id}")

        # Random Bonus (Private only)
        if is_private and random.random() < 0.1:
            prefs = await db.get_user_preferences(bot_name, user.id)
            bonus = await engine.get_random_bonus()

            if bonus:
                is_shayari = "shayari" in str(bonus).lower() or "\n" in str(bonus)
                if is_shayari and not prefs.get('shayari_enabled', True):
                    bonus = None
                elif not is_shayari and not prefs.get('meme_enabled', True):
                    bonus = None

                if bonus:
                    responses.append(bonus)

        if responses:
            if is_group:
                # Do not split group responses into multiple message chunks
                responses = ['\n\n'.join(responses)]
                
            sent_msg_ids = await send_multi_messages(
                context.bot,
                chat.id,
                responses,
                reply_to=message.message_id if is_group else None,
            )
            logger.info(f"[{bot_name}] Sent {len(responses)} msgs to {user.id}")

            # SAVE BOT'S RESPONSE TO SHARED GROUP MEMORY
            if is_group and sent_msg_ids:
                display_name = 'Niyati' if bot_name == 'niyati' else 'Palak Deva'
                for idx, msg_id in enumerate(sent_msg_ids):
                    chunk_text = responses[idx]
                    await group_manager.add_bot_message(
                        bot_name=bot_name, 
                        bot_id=context.bot.id, 
                        chat_id=chat.id, 
                        message_id=msg_id, 
                        bot_display_name=display_name, 
                        text=chunk_text, 
                        trigger_message_id=trigger_message_id
                    )
                logger.info(f"[{bot_name}] Saved response to shared group memory")

            await state_manager.record_response_outcome(bot_name, chat.id, user.id, True, decision.action)

            # ── MOOD IMAGE (very rare, private only) ──
            if is_private and should_send_image():
                detected_mood = detect_mood_from_text(user_message)
                img_url = get_mood_image(bot_name, detected_mood)
                if img_url:
                    try:
                        await context.bot.send_photo(
                            chat_id=chat.id, photo=img_url,
                        )
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
                    except Exception as e:
                        logger.debug(f"Sticker send failed: {e}")

        else:
            logger.warning(f"[{bot_name}] No responses generated for user {user.id}")
            await state_manager.record_response_outcome(bot_name, chat.id, user.id, False, decision.action)

    except Exception as e:
        logger.error(f"Message handling error ({bot_name}): {e}", exc_info=True)
        try:
            # We assume decision was made, if not, it will fail but it's safe
            await state_manager.record_response_outcome(bot_name, chat.id, user.id, False, decision.action)
        except:
            pass
            
        if is_group and 'trigger_message_id' in locals():
            await group_manager.release_bot(bot_name, chat.id, trigger_message_id)
        try:
            await message.reply_text("oops kuch gadbad... retry karo? 🫶")
        except:
            pass
