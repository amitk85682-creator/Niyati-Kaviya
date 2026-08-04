"""
╔══════════════════════════════════════════════════════╗
║              MEDIA SYSTEM                             ║
║   Mood Images + Stickers for Natural Conversations    ║
╚══════════════════════════════════════════════════════╝

Mood-based images & stickers that bots can send occasionally
to feel more real and human-like.
"""

import random
from typing import Optional

# ============================================================================
# MOOD IMAGES (URLs) - Bot randomly picks from these
# Add more URLs as needed for each bot
# ============================================================================

MOOD_IMAGES = {
    'niyati': {
        'happy': [
            "https://i.pinimg.com/736x/54/5b/07/545b07562a654b0be845b5fa45e5a4d3.jpg",
            "https://i.pinimg.com/736x/e8/dc/f6/e8dcf6a3c1a7e4a6d8a7b5c3e1f2a4b6.jpg",
        ],
        'sad': [
            "https://i.pinimg.com/736x/e1/f2/a3/e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6.jpg",
        ],
        'playful': [
            "https://i.pinimg.com/736x/a1/b2/c3/a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6.jpg",
        ],
        'sleepy': [
            "https://i.pinimg.com/736x/a3/b4/c5/a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8.jpg",
        ],
        'angry': [],
        'love': []
    },
    'Palak': {
        'happy': [
            "https://i.pinimg.com/736x/8c/3d/f1/8c3df1a2b4c5d6e7f8a9b0c1d2e3f4a5.jpg",
            "https://i.pinimg.com/736x/f2/a1/b3/f2a1b3c4d5e6f7a8b9c0d1e2f3a4b5c6.jpg",
        ],
        'sad': [
            "https://i.pinimg.com/736x/f3/a4/b5/f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8.jpg",
        ],
        'playful': [
            "https://i.pinimg.com/736x/b3/c4/d5/b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8.jpg",
        ],
        'sleepy': [
            "https://i.pinimg.com/736x/b5/c6/d7/b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0.jpg",
        ],
        'angry': [],
        'love': []
    }
}

# ============================================================================
# STICKER FILE IDS - Telegram Sticker file_ids
# These need to be real Telegram sticker file_ids.
# You can get them by forwarding stickers to @RawDataBot
# ============================================================================

CONTEXT_STICKERS = {
    'niyati': {
        'haha': [],
        'lol': [],
        'sad': [],
        'love': [],
        'angry': [],
        'hi': [],
        'bye': [],
        'thanks': [],
        'sorry': [],
        'miss': [],
    },
    'Palak': {
        'haha': [],
        'lol': [],
        'sad': [],
        'love': [],
        'angry': [],
        'hi': [],
        'bye': [],
        'thanks': [],
        'sorry': [],
        'miss': [],
    }
}


# ============================================================================
# MEDIA FUNCTIONS
# ============================================================================

# Chance of sending an image (very rare, ~3%)
IMAGE_SEND_CHANCE = 0.03

# Chance of sending a sticker (~5%)
STICKER_SEND_CHANCE = 0.05


def should_send_image() -> bool:
    """Check if bot should send an image (very rare)"""
    return random.random() < IMAGE_SEND_CHANCE


def should_send_sticker() -> bool:
    """Check if bot should send a sticker"""
    return random.random() < STICKER_SEND_CHANCE


def get_mood_image(bot_name: str, mood: str) -> Optional[str]:
    """Get a random image URL for the given mood and bot"""
    bot_images = MOOD_IMAGES.get(bot_name, {})
    
    # Try exact mood first
    images = bot_images.get(mood, [])
    if images:
        return random.choice(images)

    # Fallback to happy
    images = bot_images.get('happy', [])
    return random.choice(images) if images else None


def get_context_sticker(bot_name: str, message_text: str) -> Optional[str]:
    """Get a sticker based on message content for the specific bot"""
    bot_stickers = CONTEXT_STICKERS.get(bot_name, {})
    msg_lower = message_text.lower()

    for keyword, sticker_ids in bot_stickers.items():
        if keyword in msg_lower and sticker_ids:
            return random.choice(sticker_ids)

    return None


def detect_mood_from_text(text: str) -> str:
    """Detect mood from user's message text"""
    text_lower = text.lower()

    sad_words = ['sad', 'dukhi', 'rona', 'ro rha', 'miss', 'lonely', 'akela', 'hurt', 'pain', 'toot']
    happy_words = ['happy', 'khush', 'mast', 'badhiya', 'amazing', 'awesome', 'wow', 'yay', 'party']
    angry_words = ['angry', 'gussa', 'irritate', 'chid', 'pagal', 'stupid', 'hate']
    love_words = ['love', 'pyaar', 'dil', 'crush', 'romantic', 'valentine', 'jaanu', 'baby']
    sleepy_words = ['neend', 'sona', 'sleep', 'tired', 'thak', 'lazy', 'bore']

    if any(w in text_lower for w in sad_words):
        return 'sad'
    elif any(w in text_lower for w in love_words):
        return 'love'
    elif any(w in text_lower for w in angry_words):
        return 'angry'
    elif any(w in text_lower for w in sleepy_words):
        return 'sleepy'
    elif any(w in text_lower for w in happy_words):
        return 'happy'

    return 'happy'  # default
