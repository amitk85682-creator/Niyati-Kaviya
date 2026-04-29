"""
╔══════════════════════════════════════════════════════╗
║            CENTRAL CONFIGURATION                      ║
║     Shared config for Niyati & Kavya Bots             ║
╚══════════════════════════════════════════════════════╝
"""

import os
import sys
import logging

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
    # Supports both NIYATI_BOT_TOKEN and TELEGRAM_BOT_TOKEN env vars
    NIYATI_BOT_TOKEN = os.getenv('NIYATI_BOT_TOKEN', '') or os.getenv('TELEGRAM_BOT_TOKEN', '')
    NIYATI_BOT_USERNAME = os.getenv('BOT_USERNAME', 'Niyati_personal_bot')

    KAVYA_BOT_TOKEN = os.getenv('KAVYA_BOT_TOKEN', '')
    KAVYA_BOT_USERNAME = os.getenv('KAVYA_BOT_USERNAME', 'Kavya_bot')

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
    GROQ_MODEL = "llama-3.3-70b-versatile"

    # Gemini
    GEMINI_MODEL = "gemini-2.5-flash"
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
    # Render sets PORT env var - app MUST bind to it for health checks
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
    GROUP_RESPONSE_RATE = float(os.getenv('GROUP_RESPONSE_RATE', '0.3'))
    PRIVACY_MODE = os.getenv('PRIVACY_MODE', 'false').lower() == 'true'

    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        errors = []
        if not cls.NIYATI_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN (Niyati) required")

        if not cls.API_KEYS_LIST and not cls.GROQ_API_KEYS_LIST and not cls.GEMINI_API_KEYS_LIST:
            errors.append("At least one API key (OpenAI/Groq/Gemini) required")

        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            logger.warning("⚠️ Supabase not configured - using local storage only")

        if not cls.KAVYA_BOT_TOKEN:
            logger.warning("⚠️ KAVYA_BOT_TOKEN not set - Kavya bot will not start")

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
        elif bot_name == 'kavya':
            return {
                'token': cls.KAVYA_BOT_TOKEN,
                'username': cls.KAVYA_BOT_USERNAME,
            }
        raise ValueError(f"Unknown bot: {bot_name}")
