"""
Character module - loads personality for each bot.
"""

from characters.niyati import NIYATI_CHARACTER
from characters.kavya import KAVYA_CHARACTER

# Character registry
_CHARACTERS = {
    'niyati': NIYATI_CHARACTER,
    'kavya': KAVYA_CHARACTER,
}


def get_character(bot_name: str) -> dict:
    """
    Get character config for a bot.
    
    Returns dict with:
    - name: Display name
    - system_prompt: Base system prompt function(mood, time_period, user_name) -> str
    - greeting: Greeting message for /start
    - about: About text
    - help_text: Help text
    """
    bot_name = bot_name.lower()
    if bot_name not in _CHARACTERS:
        raise ValueError(f"Unknown character: {bot_name}. Available: {list(_CHARACTERS.keys())}")
    return _CHARACTERS[bot_name]
