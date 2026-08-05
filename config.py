"""
╔══════════════════════════════════════════════════════╗
║            CENTRAL CONFIGURATION                      ║
║     Shared config for Niyati & Palak Bots             ║
╚══════════════════════════════════════════════════════╝
"""

import os
import sys
import logging

from dotenv import load_dotenv
load_dotenv()

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger('bot')

for lib in ['httpx', 'telegram', 'openai', 'httpcore']:
    logging.getLogger(lib).setLevel(logging.WARNING)


# ============================================================================
# CONFIG CLASS
# ============================================================================

class Config:
    """Central configuration for both bots"""

    # ── Bot Tokens ──
    NIYATI_BOT_TOKEN = os.getenv('NIYATI_BOT_TOKEN', '') or os.getenv('TELEGRAM_BOT_TOKEN', '')
    NIYATI_BOT_USERNAME = os.getenv('NIYATI_BOT_USERNAME', '') or os.getenv('BOT_USERNAME', 'Niyati_personal_bot')

    PALAK_BOT_TOKEN = os.getenv('PALAK_BOT_TOKEN') or os.getenv('KAVYA_BOT_TOKEN', '')
    PALAK_BOT_USERNAME = os.getenv('PALAK_BOT_USERNAME') or os.getenv('KAVYA_BOT_USERNAME', 'palakdevabot')

    # ── AI API Keys ──
    # OpenAI
    OPENAI_API_KEYS_STR = os.getenv('OPENAI_API_KEYS', '') or os.getenv('OPENAI_API_KEY', '')
    API_KEYS_LIST = [k.strip() for k in OPENAI_API_KEYS_STR.split(',') if k.strip()]

    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '200'))
    OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.85'))

    # Groq
    GROQ_API_KEYS_STR = os.getenv('GROQ_API_KEYS', '')
    GROQ_API_KEYS_LIST = [k.strip() for k in GROQ_API_KEYS_STR.split(',') if k.strip()]
    GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')

    # Gemini
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')
    GEMINI_API_KEYS_STR = os.getenv('GEMINI_API_KEYS', '')
    GEMINI_API_KEYS_LIST = [k.strip() for k in GEMINI_API_KEYS_STR.split(',') if k.strip()]

    # ── Supabase ──
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')

    # ── Admin ──
    ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    BROADCAST_PIN = os.getenv('BROADCAST_PIN', 'niyati2024')

    # ── Limits ──
    MAX_PRIVATE_MESSAGES = int(os.getenv('MAX_PRIVATE_MESSAGES', '20'))
    MAX_GROUP_MESSAGES = int(os.getenv('MAX_GROUP_MESSAGES', '5'))
    MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '15'))
    MAX_REQUESTS_PER_DAY = int(os.getenv('MAX_REQUESTS_PER_DAY', '500'))

    # ── Memory ──
    MAX_LOCAL_USERS_CACHE = int(os.getenv('MAX_LOCAL_USERS_CACHE', '10000'))
    MAX_LOCAL_GROUPS_CACHE = int(os.getenv('MAX_LOCAL_GROUPS_CACHE', '1000'))
    CACHE_CLEANUP_INTERVAL = int(os.getenv('CACHE_CLEANUP_INTERVAL', '3600'))

    # ── Timezone ──
    DEFAULT_TIMEZONE = os.getenv('DEFAULT_TIMEZONE', 'Asia/Kolkata')

    # ── Server ──
    PORT = int(os.getenv('PORT', '10000'))

    # ── Features ──
    MULTI_MESSAGE_ENABLED = os.getenv('MULTI_MESSAGE_ENABLED', 'true').lower() == 'true'
    TYPING_DELAY_MS = int(os.getenv('TYPING_DELAY_MS', '800'))

    # ── Broadcast ──
    BROADCAST_RETRY_ATTEMPTS = int(os.getenv('BROADCAST_RETRY_ATTEMPTS', '3'))
    BROADCAST_RATE_LIMIT = float(os.getenv('BROADCAST_RATE_LIMIT', '0.05'))

    # ── Cooldown & Misc ──
    USER_COOLDOWN_SECONDS = int(os.getenv('USER_COOLDOWN_SECONDS', '3'))
    RANDOM_SHAYARI_CHANCE = float(os.getenv('RANDOM_SHAYARI_CHANCE', '0.15'))
    RANDOM_MEME_CHANCE = float(os.getenv('RANDOM_MEME_CHANCE', '0.10'))
    PROB_NIYATI_ONLY = float(os.getenv('PROB_NIYATI_ONLY', '0.30'))
    PROB_PALAK_ONLY = float(os.getenv('PROB_PALAK_ONLY', '0.30'))
    PROB_BOTH = float(os.getenv('PROB_BOTH', '0.15'))
    PROB_NONE = float(os.getenv('PROB_NONE', '0.25'))
    PROB_CHIP_IN = float(os.getenv('PROB_CHIP_IN', '0.20'))
    SECOND_BOT_DELAY = float(os.getenv('SECOND_BOT_DELAY', '2.0'))
    SECOND_BOT_TIMEOUT = float(os.getenv('SECOND_BOT_TIMEOUT', '10.0'))
    MAX_BOT_REPLIES_PER_HUMAN_MESSAGE = int(os.getenv('MAX_BOT_REPLIES_PER_HUMAN_MESSAGE', '3'))
    MAX_CONSECUTIVE_BOT_TO_BOT_REPLIES = int(os.getenv('MAX_CONSECUTIVE_BOT_TO_BOT_REPLIES', '1'))
    PRIVACY_MODE = os.getenv('PRIVACY_MODE', 'false').lower() == 'true'

    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        errors = []
        if not cls.NIYATI_BOT_TOKEN:
            errors.append("NIYATI_BOT_TOKEN (or TELEGRAM_BOT_TOKEN) required")

        if not cls.API_KEYS_LIST and not cls.GROQ_API_KEYS_LIST and not cls.GEMINI_API_KEYS_LIST:
            errors.append("At least one API key (OpenAI/Groq/Gemini) required")

        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            logger.warning("Supabase not configured - using local storage only")

        if not cls.PALAK_BOT_TOKEN:
            logger.warning("PALAK_BOT_TOKEN not set - Palak bot will not start")
        elif cls.PALAK_BOT_TOKEN == cls.NIYATI_BOT_TOKEN:
            errors.append("NIYATI_BOT_TOKEN and PALAK_BOT_TOKEN cannot be the same! You must create a second bot in BotFather for Palak.")

        if errors:
            raise ValueError(f"Config errors: {', '.join(errors)}")

    @classmethod
    def get_bot_config(cls, bot_name: str) -> dict:
        """Get bot-specific config"""
        if bot_name == 'niyati':
            return {
                'token': cls.NIYATI_BOT_TOKEN,
                'username': cls.NIYATI_BOT_USERNAME,
            }
        elif bot_name == 'palak':
            return {
                'token': cls.PALAK_BOT_TOKEN,
                'username': cls.PALAK_BOT_USERNAME,
            }
        raise ValueError(f"Unknown bot: {bot_name}")
