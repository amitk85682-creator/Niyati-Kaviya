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
        import re
        if not user_message:
            return ''
            
        msg_lower = user_message.lower()
        
        if re.search(r'\b(outfit|kya pehna|look dikhao)\b', msg_lower):
            return 'outfit'
            
        if re.search(r'\b(location|kahan ho|cafe dikhao)\b', msg_lower):
            return 'location'
            
        has_pic = bool(re.search(r'\b(pic|pics|photo|photos|selfie|tasvir|image)\b', msg_lower))
        has_req = bool(re.search(r'\b(send|bhej|bhejo|dikha|dikhao|dekha|de|kro|karo)\b', msg_lower))
        
        if (has_pic and has_req) or bool(re.search(r'\b(apni pic|tumhari pic|apni photo|tum kaisi lag rahi ho)\b', msg_lower)):
            return 'selfie'
            
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
                     bot_context_text: str = None,
                     state = None) -> MediaDecision:
        """Decide whether to send media in this turn"""
        if not Config.MEDIA_ENABLED:
            return MediaDecision(should_send=False, reason="media_disabled")
            
        req_type = MediaDecisionEngine._is_direct_request(user_message)
        last_shared = await MediaMemory.get_last_shared(bot_name, chat_id, user_id)
        
        # 1. Direct Request
        if req_type or (bot_context_text and 'dikhao' in user_message.lower()):
            trigger_type = req_type if req_type else 'contextual_dikhao'
            
            # Apply resistance logic
            if state:
                state.dialogue.consecutive_media_requests += 1
                req_count = state.dialogue.consecutive_media_requests
                
                if req_count == 1:
                    logger.info(f"[MediaDecision] bot={bot_name} should_send=False reason=resist_1")
                    return MediaDecision(should_send=False, reason="resist_1")
                elif req_count == 2:
                    logger.info(f"[MediaDecision] bot={bot_name} should_send=False reason=resist_2")
                    return MediaDecision(should_send=False, reason="resist_2")
                else:
                    # 3rd time's the charm, yield and reset
                    state.dialogue.consecutive_media_requests = 0
            
            media = await MediaSelector.select_media(
                bot_name=bot_name, 
                request_type=trigger_type,
                scene=current_scene
            )
            
            if media:
                logger.info(f"[MediaDecision] bot={bot_name} should_send=True reason=direct_request:{trigger_type}")
                return MediaDecision(should_send=True, reason=f"direct_request_yield:{trigger_type}", selected_media_id=media.media_id, trigger_type=trigger_type, confidence=1.0)
            else:
                return MediaDecision(should_send=False, reason=f"no_media_found_for:{trigger_type}")
        elif state and state.dialogue.consecutive_media_requests > 0:
            # If they stop asking (no trigger), gently decay or reset. 
            # For simplicity, if they talk about something else, reset it.
            # But wait, what if they say "pls bhej do"? That might not hit the regex.
            # If it doesn't hit the regex, maybe we shouldn't reset instantly unless it's a completely different topic.
            # We'll just reset it to 0 if it's a long message without any request keywords.
            if len(user_message.split()) > 5:
                state.dialogue.consecutive_media_requests = 0
                
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
