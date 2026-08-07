from database import db
from media_models import CharacterMedia
from typing import List

class MediaVault:
    @staticmethod
    async def get_all_media(bot_name: str) -> List[CharacterMedia]:
        """Fetch all active media for a specific bot from the vault"""
        media_dicts = await db.get_all_character_media(bot_name)
        return [CharacterMedia.from_dict(m) for m in media_dicts]

    @staticmethod
    async def save_media(media: CharacterMedia) -> bool:
        """Save or update media in the vault"""
        return await db.upsert_character_media(media.to_dict())

    @staticmethod
    async def increment_use_count(media_id: str, bot_name: str) -> bool:
        """Increment the use_count of a specific media and update last_used_at"""
        media_dicts = await db.get_all_character_media(bot_name)
        for m_dict in media_dicts:
            if m_dict['media_id'] == media_id:
                m_dict['use_count'] = m_dict.get('use_count', 0) + 1
                from datetime import datetime, timezone
                m_dict['last_used_at'] = datetime.now(timezone.utc).isoformat()
                return await db.upsert_character_media(m_dict)
        return False
