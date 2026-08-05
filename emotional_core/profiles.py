"""
Immutable trait profiles for characters.
"""
import types

_NIYATI_TRAITS = types.MappingProxyType({
    "warmth": 0.82,
    "expressiveness": 0.78,
    "social_confidence": 0.68,
    "sensitivity": 0.72,
    "playfulness": 0.75,
    "sarcasm": 0.48,
    "impulsiveness": 0.62,
    "patience": 0.58,
    "autonomy": 0.52,
    "conflict_avoidance": 0.45
})

_PALAK_TRAITS = types.MappingProxyType({
    "warmth": 0.64,
    "expressiveness": 0.42,
    "social_confidence": 0.44,
    "sensitivity": 0.68,
    "playfulness": 0.58,
    "sarcasm": 0.72,
    "impulsiveness": 0.30,
    "patience": 0.66,
    "autonomy": 0.78,
    "conflict_avoidance": 0.58
})

def get_character_traits(bot_name: str) -> types.MappingProxyType:
    if bot_name.lower() == 'niyati':
        return _NIYATI_TRAITS
    return _PALAK_TRAITS
