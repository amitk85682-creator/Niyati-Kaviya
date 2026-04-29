"""
╔══════════════════════════════════════════════════════╗
║              MEDIA SYSTEM                             ║
║   Mood Images + Stickers for Natural Conversations    ║
╚══════════════════════════════════════════════════════╝

Mood-based images & stickers that bots can send occasionally
to feel more real and human-like.
"""

import random
from config import logger

# ============================================================================
# MOOD IMAGES (URLs) - Bot randomly picks from these
# Add more URLs as needed for each bot
# ============================================================================

MOOD_IMAGES = {
    'niyati': {
        'happy': [
            "https://i.pinimg.com/736x/17/34/51/173451aa6ff33fb84fe9d50843ae4f76.jpg",
            "https://i.pinimg.com/736x/a7/f7/b0/a7f7b0781fd3a5ef1a249811742172a9.jpg",
            "https://i.pinimg.com/736x/f0/05/ea/f005eabd65021d7fdcd7606145fa8ca1.jpg",
        ],
        'sad': [
            "https://i.pinimg.com/1200x/de/6a/93/de6a93d6c5ed7b402f2414e9bbcbad86.jpg",
            "https://i.pinimg.com/736x/96/f6/1b/96f61b5ad071b1ad56de9488ed2ba8b7.jpg",
        ],
        'playful': [
            "https://i.pinimg.com/1200x/61/69/f4/6169f4853c3dbd7eeddbb6d6bc2ac947.jpg",
            "https://i.pinimg.com/736x/86/74/4b/86744bf9394b0bfacf217468aec4cb09.jpg",
        ],
        'sleepy': [
            "https://i.pinimg.com/736x/96/f6/1b/96f61b5ad071b1ad56de9488ed2ba8b7.jpg",
            "https://i.pinimg.com/736x/2f/e1/d3/2fe1d39dbea4c2e7c9c000cf4f0e9b1b.jpg",
        ],
        'angry': [
            "https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEiVcIC3KTBMsHKeMSQj3LVBQYS799QfBsB7TJW8C1EJX0WeVxow86z2cg6RS_ov2EdENy6ZJR2CrfuXqCeTEbzP8m1pN7H8SH-ftxi1M19UWveEslz4M9IrUsA5Uv152-vjo8NsDymyYNF61nZTsMYyCs3tQ2mv7cFqgdLTKSig98UfWlTXaJMzcxn1kOs/s1600/download.jpeg3.jpeg",
        ],
        'love': [
            "https://i.pinimg.com/736x/cc/4c/0c/cc4c0cdd336fff3e18452d4edc14b7fe.jpg",
            "https://i.pinimg.com/736x/e3/9d/9b/e39d9bce399a06f375f778d0e96189be.jpg",
        ]
    },
    'kavya': {
        'happy': [
            "https://i.pinimg.com/736x/a6/db/53/a6db538340f0026d0b878cec25ae9c7d.jpg",
            "https://i.pinimg.com/736x/1d/24/0f/1d240f329a97f9e16aac1e884fee6465.jpg",
        ],
        'sad': [
            "https://i.pinimg.com/736x/3f/93/8e/3f938e23df23787399ab43b4a4dcc1a3.jpg",
        ],
        'playful': [
            "https://i.pinimg.com/736x/4d/a8/e4/4da8e401d04f7fdc9fbacf06a2e27434.jpg",
            "https://i.pinimg.com/736x/4f/b9/ed/4fb9ed5d487538ee96fc91e7151217a5.jpg",
        ],
        'sleepy': [
            "https://i.pinimg.com/736x/54/82/e5/5482e58183a8a0df1ffa44a12629a201.jpg",
        ],
        'angry': [
            "https://i.pinimg.com/736x/fb/0d/54/fb0d549943cbb89b5d522d3592157ca2.jpg",
        ],
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
        'haha': [851580814],
        'lol': [851580824],
        'sad': [851580825],
        'love': [851580826],
        'angry': [851580828],
        'hi': [851580830],
        'bye': [851580833],
        'thanks': [851580838],
        'sorry': [851580842],
        'miss': [851580847],
    },
    'kavya': {
        'haha': [851580814],
        'lol': [851580824],
        'sad': [851580825],
        'love': [851580826],
        'angry': [851580828],
        'hi': [851580830],
        'bye': [851580833],
        'thanks': [851580838],
        'sorry': [851580842],
        'miss': [851580847],
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


def get_mood_image(bot_name: str, mood: str) -> str | None:
    """Get a random image URL for the given mood and bot"""
    bot_images = MOOD_IMAGES.get(bot_name, {})
    
    # Try exact mood first
    images = bot_images.get(mood, [])
    if images:
        return random.choice(images)

    # Fallback to happy
    images = bot_images.get('happy', [])
    return random.choice(images) if images else None


def get_context_sticker(bot_name: str, message_text: str) -> str | None:
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
