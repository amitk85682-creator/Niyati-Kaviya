import re
from typing import Dict, Any
from config import Config, logger
from media_models import CharacterMedia
from media_vault import MediaVault

class MediaIndexer:
    @staticmethod
    def parse_caption(caption: str) -> Dict[str, Any]:
        """Parse hashtags and key-value styles from caption"""
        metadata = {
            "tags": [],
            "scene": None,
            "time_bucket": None,
            "mood": None,
            "outfit": None,
            "pose": None,
            "people_present": None,
            "use_for": []
        }
        if not caption:
            return metadata
            
        lines = caption.lower().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Key-value style parsing
            if '=' in line:
                parts = line.split('=', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip()
                    # Normalize some common synonyms
                    if key in ['time', 'time_bucket']:
                        key = 'time_bucket'
                        if val == 'nighttime': val = 'night'
                    elif key in ['location', 'place', 'scene']:
                        key = 'scene'
                        if val == 'coffee_shop': val = 'cafe'
                        
                    if key in metadata and key != 'tags' and key != 'use_for':
                        metadata[key] = val
                    elif key == 'use_for':
                        metadata['use_for'] = [v.strip() for v in val.split(',')]
            else:
                # Hashtag style parsing
                words = line.split()
                for word in words:
                    if word.startswith('#'):
                        tag = word[1:].strip()
                        if tag:
                            metadata['tags'].append(tag)
                            
        # Basic derivation if no structured metadata
        caption_lower = caption.lower()
        if not metadata['scene']:
            if 'cafe' in caption_lower or 'coffee' in caption_lower:
                metadata['scene'] = 'cafe'
            elif 'room' in caption_lower or 'home' in caption_lower:
                metadata['scene'] = 'home'
                
        if not metadata['pose']:
            if 'selfie' in caption_lower:
                metadata['pose'] = 'selfie'
                
        return metadata

    @staticmethod
    async def handle_channel_post(update_type: str, message: Any, bot_name: str):
        """Handle new or edited channel post"""
        if not message.chat or message.chat.type != 'channel':
            return
            
        chat_id = message.chat.id
        
        # Verify if this channel matches bot_name's configured channel
        if bot_name == 'niyati' and chat_id != Config.NIYATI_MEDIA_CHANNEL_ID:
            return
        if bot_name == 'palak' and chat_id != Config.PALAK_MEDIA_CHANNEL_ID:
            return
            
        if not message.photo and not message.document:
            return
            
        media_type = "photo"
        if message.document:
            media_type = "document"
             
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document:
            if message.document.mime_type and message.document.mime_type.startswith('image/'):
                file_id = message.document.file_id
            else:
                return # Skip non-image documents
             
        caption = message.caption or ""
        metadata = MediaIndexer.parse_caption(caption)
        
        media_id = f"{bot_name}_{chat_id}_{message.message_id}"
        
        media = CharacterMedia(
            media_id=media_id,
            bot_name=bot_name,
            channel_id=chat_id,
            channel_message_id=message.message_id,
            media_type=media_type,
            telegram_file_id=file_id,
            caption_raw=caption,
            tags=tuple(metadata['tags']),
            scene=metadata['scene'],
            time_bucket=metadata['time_bucket'],
            mood=metadata['mood'],
            outfit=metadata['outfit'],
            pose=metadata['pose'],
            people_present=metadata['people_present'],
            use_for=metadata['use_for']
        )
        
        success = await MediaVault.save_media(media)
        if success:
             logger.info(f"[Index] bot={bot_name} {update_type}={message.message_id} tags={list(media.tags)}")
