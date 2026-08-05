import re
import random
import hashlib
from typing import Dict, Tuple, List, Optional
from datetime import datetime, timezone, timedelta
import asyncio
from config import logger, Config

from .models import TurnPlan, ConversationSession

class ConversationDirector:
    """
    Central Conversation Director shared by all bots.
    Evaluates group chat messages once and produces an immutable TurnPlan.
    """
    def __init__(self):
        self._sessions: Dict[Tuple[int, int], ConversationSession] = {}
        self._turn_plans: Dict[Tuple[int, int], TurnPlan] = {}
        self._lock = asyncio.Lock()
        
    def _get_session_key(self, chat_id: int, user_id: int) -> Tuple[int, int]:
        return (chat_id, user_id)
        
    def _cleanup_expired(self, now: datetime):
        expired = [k for k, s in self._sessions.items() if s.expires_at and now > s.expires_at]
        for k in expired:
            del self._sessions[k]

    def clear(self):
        self._sessions.clear()
        self._turn_plans.clear()
            
    async def plan_turn(self, chat_id: int, user_id: int, user_name: str, 
                        message_id: int, text: str, 
                        reply_to_bot_name: Optional[str] = None,
                        is_group: bool = True) -> TurnPlan:
        async with self._lock:
            now = datetime.now(timezone.utc)
            self._cleanup_expired(now)
            
            plan_key = (chat_id, message_id)
            if plan_key in self._turn_plans:
                return self._turn_plans[plan_key]
                
            key = self._get_session_key(chat_id, user_id)
            if key not in self._sessions:
                self._sessions[key] = ConversationSession(chat_id=chat_id, user_id=user_id)
                
            session = self._sessions[key]
            
            text_lower = text.lower()
            explicit_target = None
            selected_bots = []
            reason = "general_fallback"
            resolved_intent = "unknown"
            reference_type = None
            normalized_question = None
            
            # --- Active Bot Precedence ---
            # 1. Telegram reply target
            if reply_to_bot_name:
                explicit_target = reply_to_bot_name
                reason = "telegram_reply"
            # 2. Explicit @username
            elif f"@{Config.NIYATI_BOT_USERNAME.lower()}" in text_lower:
                explicit_target = "niyati"
                reason = "explicit_mention"
            elif f"@{Config.PALAK_BOT_USERNAME.lower()}" in text_lower:
                explicit_target = "palak"
                reason = "explicit_mention"
            # 3. Explicit plural
            elif "dono" in text_lower or "both" in text_lower or ("niyati" in text_lower and "palak" in text_lower):
                explicit_target = "both"
                reason = "explicit_both"
            # 4. Explicit character name
            elif bool(re.search(r'\b(niyati)\b', text_lower)) and not bool(re.search(r'\b(palak|palakdevabot)\b', text_lower)):
                explicit_target = "niyati"
                reason = "explicit_name"
            elif bool(re.search(r'\b(palak|palakdevabot)\b', text_lower)) and not bool(re.search(r'\b(niyati)\b', text_lower)):
                explicit_target = "palak"
                reason = "explicit_name"
            # 5. Semantic entity owner
            elif bool(re.search(r'\b(arjun|mochi)\b', text_lower)) or ("delhi" in text_lower and any(w in text_lower for w in ["kaha", "kahan", "rehti", "city", "se ho"])):
                explicit_target = "niyati"
                reason = "entity_owner:niyati"
            elif bool(re.search(r'\b(bruno|palakcreates)\b', text_lower)) or ("mumbai" in text_lower and any(w in text_lower for w in ["kaha", "kahan", "rehti", "city", "se ho"])):
                explicit_target = "palak"
                reason = "entity_owner:palak"
            # 6. Short follow-up/reference
            elif (text_lower.strip(' ?!') in ["ku", "kyu", "why", "kaise", "how", "fir", "then", "acha", "sach", "kon", "kab", "or batao", "matlab", "really", "achha"] or len(text_lower.split()) <= 2) and session.active_bot:
                explicit_target = session.active_bot
                reason = "short_followup:last_speaker"
                if text_lower.strip(' ?!') in ["ku", "kyu", "why"]:
                    resolved_intent = "ASK_REASON"
                elif text_lower.strip(' ?!') in ["matlab", "kaise"]:
                    resolved_intent = "ASK_CLARIFICATION"
                else:
                    resolved_intent = "CONTINUE_TOPIC"
                    
                if session.last_topic and session.last_topic.startswith("current_"):
                    reference_type = "claim"
            # 7. Existing active bot
            elif session.active_bot:
                explicit_target = session.active_bot
                reason = "active_bot_continuation"
            # 8. Deterministic fallback
            else:
                seed_str = f"{chat_id}:{message_id}"
                seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
                rng = random.Random(seed_int)
                roll = rng.random()
                explicit_target = "niyati" if roll < 0.5 else "palak"
                reason = "deterministic_fallback"

            # --- Correction Handling ---
            is_correction = False
            if "maine toh niyati se" in text_lower or "niyati se pucha" in text_lower or "niyati se baat" in text_lower:
                explicit_target = "niyati"
                is_correction = True
            elif "maine toh palak se" in text_lower or "palak se pucha" in text_lower or "palak se baat" in text_lower:
                explicit_target = "palak"
                is_correction = True
                
            if is_correction and session.pending_question:
                normalized_question = session.pending_question
                reason = "user_correction"
                resolved_intent = "correction"
                logger.info(f"[Director] switched_to={explicit_target} reason=user_correction")

            # --- Determine Selection ---
            if explicit_target == "both":
                selected_bots = ["niyati", "palak"]
            else:
                selected_bots = [explicit_target]

            # --- Pre-Update Session (Plan only, do not save claims or last bot message yet) ---
            if "?" in text or any(w in text_lower.split() for w in ["kya", "kaise", "kyu", "kon", "kab"]):
                if not is_correction:
                    session.pending_question = text
                    normalized_question = text

            session.last_human_message_id = message_id
            
            plan = TurnPlan(
                chat_id=chat_id,
                human_user_id=user_id,
                human_message_id=message_id,
                selected_bots=selected_bots,
                primary_bot=selected_bots[0] if selected_bots else None,
                explicit_target=explicit_target if explicit_target != "both" else None,
                active_bot=session.active_bot,
                referenced_bot=session.last_bot_name,
                referenced_message_id=session.last_bot_message_id,
                active_topic=session.last_topic,
                resolved_intent=resolved_intent,
                reference_type=reference_type,
                normalized_question=normalized_question,
                reason=reason,
                conversation_session_id=f"{chat_id}_{user_id}_{session.active_since.timestamp() if session.active_since else now.timestamp()}"
            )
            self._turn_plans[plan_key] = plan
            
            # Keep map small
            if len(self._turn_plans) > 1000:
                keys_to_delete = list(self._turn_plans.keys())[:100]
                for k in keys_to_delete:
                    del self._turn_plans[k]
                    
            return plan

    async def record_turn_outcome(self, chat_id: int, user_id: int, bot_name: str, message_id: int, claim_type: Optional[str] = None):
        async with self._lock:
            now = datetime.now(timezone.utc)
            key = self._get_session_key(chat_id, user_id)
            if key not in self._sessions:
                self._sessions[key] = ConversationSession(chat_id=chat_id, user_id=user_id)
            session = self._sessions[key]
            session.active_bot = bot_name
            session.active_since = session.active_since or now
            session.last_bot_name = bot_name
            session.last_bot_message_id = message_id
            session.recent_turns += 1
            session.expires_at = now + timedelta(minutes=10)
            if claim_type:
                session.last_topic = claim_type

# Singleton
director = ConversationDirector()
