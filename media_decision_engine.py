import random
from datetime import datetime, timezone
from config import Config, logger
from media_models import MediaDecision, LastSharedMedia
from media_selector import MediaSelector
from media_memory import MediaMemory

class MediaDecisionEngine:
    @staticmethod
    def _is_direct_request(user_message: str) -> str:
        """Determine if user directly asked for media"""
        if not user_message:
            return ''
            
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ['aaj ka look dikhao', 'outfit dikhao', 'kya pehna hai']):
            return 'outfit'
        if any(w in msg_lower for w in ['selfie bhejo', 'pic send karo', 'photo bhejo', 'tum kaisi lag rahi ho']):
            return 'selfie'
        if any(w in msg_lower for w in ['location ki pic bhejo', 'kahan ho', 'cafe dikhao']):
            return 'location'
        if 'dikhao' in msg_lower:
            return 'general'
        return ''

    @staticmethod
    async def decide(bot_name: str, 
                     user_message: str, 
                     chat_id: int,
                     user_id: int,
                     is_group: bool, 
                     current_scene: str = None, 
                     bot_context_text: str = None) -> MediaDecision:
        """Decide whether to send media in this turn"""
        if not Config.MEDIA_ENABLED:
            return MediaDecision(should_send=False, reason="media_disabled")
            
        req_type = MediaDecisionEngine._is_direct_request(user_message)
        last_shared = await MediaMemory.get_last_shared(bot_name, chat_id, user_id)
        
        # 1. Direct Request
        if req_type or (bot_context_text and 'dikhao' in user_message.lower()):
            trigger_type = req_type if req_type else 'contextual_dikhao'
            media = await MediaSelector.select_media(
                bot_name=bot_name, 
                request_type=trigger_type,
                scene=current_scene
            )
            
            if media:
                logger.info(f"[MediaDecision] bot={bot_name} should_send=True reason=direct_request:{trigger_type}")
                return MediaDecision(should_send=True, reason=f"direct_request:{trigger_type}", selected_media_id=media.media_id, trigger_type=trigger_type, confidence=1.0)
            else:
                return MediaDecision(should_send=False, reason=f"no_media_found_for:{trigger_type}")
                
        # 2. Spontaneous share rules
        if last_shared:
            now = datetime.now(timezone.utc)
            try:
                sent_time = datetime.fromisoformat(last_shared.sent_at)
                diff_minutes = (now - sent_time).total_seconds() / 60
                if diff_minutes < getattr(Config, 'MEDIA_SPONTANEOUS_COOLDOWN_MINUTES', 20):
                    return MediaDecision(should_send=False, reason="cooldown")
            except Exception as e:
                logger.warning(f"Error parsing date {last_shared.sent_at}: {e}")
                
        # Very rare spontaneous share (e.g. 2% chance per message if cooldown passed)
        if random.random() < 0.02:
            media = await MediaSelector.select_media(bot_name=bot_name, request_type='spontaneous')
            if media:
                logger.info(f"[MediaDecision] bot={bot_name} should_send=True reason=spontaneous")
                return MediaDecision(should_send=True, reason="spontaneous", selected_media_id=media.media_id, trigger_type="spontaneous", confidence=0.8)
                
        return MediaDecision(should_send=False, reason="no_trigger")
