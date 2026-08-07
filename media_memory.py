from database import db
from media_models import LastSharedMedia
from typing import Optional

class MediaMemory:
    @staticmethod
    async def save_last_shared(memory: LastSharedMedia) -> bool:
        """Save the last shared media memory for contextual reference"""
        return await db.save_last_shared_media(memory.to_dict())

    @staticmethod
    async def get_last_shared(bot_name: str, chat_id: int, user_id: int) -> Optional[LastSharedMedia]:
        """Retrieve the last shared media memory for a specific conversation"""
        data = await db.get_last_shared_media(bot_name, chat_id, user_id)
        if data:
            return LastSharedMedia.from_dict(data)
        return None
