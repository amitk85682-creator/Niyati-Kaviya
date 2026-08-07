import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Tuple, Optional


@dataclass
class CharacterMedia:
    media_id: str
    bot_name: str
    channel_id: int
    channel_message_id: int
    media_type: str = "photo"
    telegram_file_id: Optional[str] = None
    caption_raw: str = ""
    tags: Tuple[str, ...] = field(default_factory=tuple)
    scene: Optional[str] = None
    time_bucket: Optional[str] = None
    mood: Optional[str] = None
    outfit: Optional[str] = None
    pose: Optional[str] = None
    people_present: Optional[str] = None
    use_for: List[str] = field(default_factory=list)
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used_at: Optional[str] = None
    use_count: int = 0

    def to_dict(self):
        d = asdict(self)
        # convert tuple to list for json serialization
        d['tags'] = list(self.tags)
        # store complex types as json strings if needed for simple db storage,
        # but supabase insert takes dicts and handles jsonb.
        return d
    
    @classmethod
    def from_dict(cls, data: dict):
        if 'tags' in data and isinstance(data['tags'], list):
            data['tags'] = tuple(data['tags'])
        return cls(**data)


@dataclass
class LastSharedMedia:
    bot_name: str
    chat_id: int
    user_id: int
    media_id: str
    channel_message_id: int
    scene: Optional[str]
    mood: Optional[str]
    outfit: Optional[str]
    sent_at: str
    caption_summary: str
    source_turn_message_id: int

    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


@dataclass
class MediaDecision:
    should_send: bool
    reason: str
    selected_media_id: Optional[str] = None
    trigger_type: str = ""
    confidence: float = 0.0
