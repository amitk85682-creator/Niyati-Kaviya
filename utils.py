"""
╔══════════════════════════════════════════════════════╗
║              UTILITIES                                ║
║   Time, Mood, Fonts, Filters, Message Sender          ║
╚══════════════════════════════════════════════════════╝
"""

import re
import random
import asyncio
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from collections import defaultdict, deque

import pytz
from telegram import Message, MessageEntity
from telegram.constants import ParseMode, ChatAction

from config import Config, logger


# ============================================================================
# TIME AWARENESS
# ============================================================================

class TimeAware:
    """Time-aware responses"""

    @staticmethod
    def get_ist_time() -> datetime:
        ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
        return datetime.now(timezone.utc).astimezone(ist)

    @staticmethod
    def get_time_period() -> str:
        hour = TimeAware.get_ist_time().hour
        if 5 <= hour < 11:
            return 'morning'
        elif 11 <= hour < 16:
            return 'afternoon'
        elif 16 <= hour < 20:
            return 'evening'
        elif 20 <= hour < 24:
            return 'night'
        else:
            return 'late_night'

    @staticmethod
    def get_greeting() -> str:
        period = TimeAware.get_time_period()
        greetings = {
            'morning': ["good morning ☀️", "uth gaye?", "subah subah! ✨"],
            'afternoon': ["heyyy", "lunch ho gaya?", "afternoon vibes 🌤️"],
            'evening': ["hiii 💫", "chai time! ☕", "shaam ho gayi yaar"],
            'night': ["heyy 🌙", "night owl?", "aaj kya plan hai"],
            'late_night': ["aap bhi jaag rahe? 👀", "insomnia gang 🦉", "neend nahi aa rahi?"]
        }
        return random.choice(greetings.get(period, ["hiii 💫"]))


# ============================================================================
# MOOD SYSTEM
# ============================================================================

class Mood:
    """Mood management"""

    MOODS = ['happy', 'playful', 'soft', 'sleepy', 'dramatic']

    @staticmethod
    def get_random_mood() -> str:
        hour = TimeAware.get_ist_time().hour
        if 6 <= hour < 12:
            weights = [0.4, 0.3, 0.2, 0.05, 0.05]
        elif 12 <= hour < 18:
            weights = [0.3, 0.35, 0.2, 0.1, 0.05]
        elif 18 <= hour < 23:
            weights = [0.25, 0.3, 0.25, 0.1, 0.1]
        else:
            weights = [0.15, 0.15, 0.3, 0.3, 0.1]
        return random.choices(Mood.MOODS, weights=weights, k=1)[0]

    @staticmethod
    def get_mood_emoji(mood: str) -> str:
        emojis = {'happy': '😊', 'playful': '😏', 'soft': '🥺', 'sleepy': '😴', 'dramatic': '😤'}
        return emojis.get(mood, '✨')


# ============================================================================
# HTML STYLISH FONTS
# ============================================================================

class StylishFonts:
    """HTML stylish text formatting"""

    @staticmethod
    def bold(text: str) -> str:
        return f"<b>{text}</b>"

    @staticmethod
    def italic(text: str) -> str:
        return f"<i>{text}</i>"

    @staticmethod
    def underline(text: str) -> str:
        return f"<u>{text}</u>"

    @staticmethod
    def strike(text: str) -> str:
        return f"<s>{text}</s>"

    @staticmethod
    def code(text: str) -> str:
        return f"<code>{text}</code>"

    @staticmethod
    def spoiler(text: str) -> str:
        return f"<tg-spoiler>{text}</tg-spoiler>"

    @staticmethod
    def link(text: str, url: str) -> str:
        return f'<a href="{url}">{text}</a>'

    @staticmethod
    def mention(name: str, user_id: int) -> str:
        return f'<a href="tg://user?id={user_id}">{name}</a>'

    @staticmethod
    def blockquote(text: str) -> str:
        return f"<blockquote>{text}</blockquote>"

    @staticmethod
    def fancy_header(text: str) -> str:
        return f"✨ <b>{text}</b> ✨"


# ============================================================================
# CONTENT FILTER
# ============================================================================

class ContentFilter:
    """Safety content filter"""

    SENSITIVE_PATTERNS = [
        r'\b(password|pin|cvv|card\s*number|otp)\b',
        r'\b\d{12,16}\b',
    ]

    DISTRESS_KEYWORDS = [
        'suicide', 'kill myself', 'want to die', 'end my life',
        'hurt myself', 'no reason to live'
    ]

    @staticmethod
    def contains_sensitive(text: str) -> bool:
        text_lower = text.lower()
        for pattern in ContentFilter.SENSITIVE_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        return False

    @staticmethod
    def detect_distress(text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in ContentFilter.DISTRESS_KEYWORDS)


# ============================================================================
# RATE LIMITER
# ============================================================================

class RateLimiter:
    """Rate limiting with cooldown system"""

    def __init__(self):
        # Keys are strings: "{bot_name}_{user_id}"
        self.requests = defaultdict(lambda: {'minute': deque(), 'day': deque()})
        self.cooldowns: Dict[str, datetime] = {}
        self.lock = asyncio.Lock()
        self._last_cleanup = datetime.now(timezone.utc)

    async def check(self, bot_name: str, user_id: int) -> Tuple[bool, str]:
        """Check rate limits (bot-aware)"""
        now = datetime.now(timezone.utc)
        key = f"{bot_name}_{user_id}"

        async with self.lock:
            # Check cooldown
            if key in self.cooldowns:
                last_time = self.cooldowns[key]
                if (now - last_time).total_seconds() < Config.USER_COOLDOWN_SECONDS:
                    return False, "cooldown"

            reqs = self.requests[key]

            # Clean old requests
            while reqs['minute'] and reqs['minute'][0] < now - timedelta(minutes=1):
                reqs['minute'].popleft()

            while reqs['day'] and reqs['day'][0] < now - timedelta(days=1):
                reqs['day'].popleft()

            # Check limits
            if len(reqs['minute']) >= Config.MAX_REQUESTS_PER_MINUTE:
                return False, "minute"
            if len(reqs['day']) >= Config.MAX_REQUESTS_PER_DAY:
                return False, "day"

            # Record request
            reqs['minute'].append(now)
            reqs['day'].append(now)
            self.cooldowns[key] = now
            return True, ""

    def get_daily_total(self, bot_name: str = None) -> int:
        """Get total daily requests, optionally filtered by bot"""
        if bot_name:
            return sum(len(r['day']) for k, r in self.requests.items() if k.startswith(f"{bot_name}_"))
        return sum(len(r['day']) for r in self.requests.values())

    async def cleanup_cooldowns(self):
        """Remove old cooldowns"""
        now = datetime.now(timezone.utc)

        if (now - self._last_cleanup).total_seconds() < 3600:
            return

        async with self.lock:
            expired = [uid for uid, t in self.cooldowns.items() if (now - t).total_seconds() > 3600]
            for uid in expired:
                del self.cooldowns[uid]

            expired_req = [uid for uid, r in self.requests.items() if not r['day']]
            for uid in expired_req:
                del self.requests[uid]

            self._last_cleanup = now


# Singleton
rate_limiter = RateLimiter()


# ============================================================================
# SMART REPLY/MENTION DETECTION
# ============================================================================

def is_user_talking_to_others(message: Message, bot_username: str, bot_id: int, bot_name: str = "") -> bool:
    """
    Check if user is replying to another HUMAN user OR mentioning other HUMAN users.
    Returns True if bot should NOT respond.
    
    🔴 FIX: If user replies to the OTHER BOT, we return False 
    (don't skip) — so both bots get a chance to participate.
    This creates the "3 real people chatting" feel.
    """
    text = message.text or ""
    bot_username_lower = bot_username.lower().lstrip('@')

    # CASE 1: Check if user is REPLYING to someone else
    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user = message.reply_to_message.from_user

        # If replied to THIS bot → definitely respond
        if replied_user.id == bot_id:
            return False

        # If replied to ANOTHER BOT → DON'T skip (let cross-bot logic handle it)
        if replied_user.is_bot:
            return False

        # If replied to a REAL USER (not a bot) → skip unless bot is mentioned
        if replied_user.username:
            if replied_user.username.lower() != bot_username_lower:
                if f"@{bot_username_lower}" not in text.lower() and (not bot_name or bot_name.lower() not in text.lower()):
                    return True
        else:
            if f"@{bot_username_lower}" not in text.lower() and (not bot_name or bot_name.lower() not in text.lower()):
                return True

    # CASE 2: Check for @mentions of other users (not bots)
    if message.entities:
        bot_mentioned = False
        other_user_mentioned = False

        for entity in message.entities:
            if entity.type == MessageEntity.MENTION:
                start = entity.offset
                end = entity.offset + entity.length
                mentioned_username = text[start:end].lstrip('@').lower()

                if mentioned_username == bot_username_lower:
                    bot_mentioned = True
                else:
                    other_user_mentioned = True

            elif entity.type == MessageEntity.TEXT_MENTION:
                if entity.user:
                    if entity.user.id == bot_id:
                        bot_mentioned = True
                    else:
                        other_user_mentioned = True

        if other_user_mentioned and not bot_mentioned:
            return True

    return False


# ============================================================================
# MESSAGE SENDER
# ============================================================================

async def send_multi_messages(bot, chat_id: int, messages: List[str],
                               reply_to: int = None, parse_mode: str = None) -> List[int]:
    """Send multiple messages with natural delays and return their message IDs"""
    sent_ids = []
    for i, msg in enumerate(messages):
        if not msg or not msg.strip():
            continue

        if i > 0:
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except:
                pass

            if Config.MULTI_MESSAGE_ENABLED:
                delay = (Config.TYPING_DELAY_MS / 1000) + random.uniform(0.2, 0.8)
            else:
                delay = 0.1
            await asyncio.sleep(delay)

        try:
            sent_msg = await bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_to_message_id=reply_to if i == 0 else None,
                parse_mode=parse_mode
            )
            sent_ids.append(sent_msg.message_id)
        except Exception as e:
            logger.error(f"Send error: {e}")
            
    return sent_ids
