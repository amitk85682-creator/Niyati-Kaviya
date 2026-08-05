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
        self._lock = asyncio.Lock()
        
    def _get_session_key(self, chat_id: int, user_id: int) -> Tuple[int, int]:
        return (chat_id, user_id)
        
    def _cleanup_expired(self, now: datetime):
        expired = [k for k, s in self._sessions.items() if s.expires_at and now > s.expires_at]
        for k in expired:
            del self._sessions[k]
            
    async def process_message(self, chat_id: int, user_id: int, user_name: str, 
                              message_id: int, text: str, 
                              reply_to_bot_name: Optional[str] = None,
                              is_group: bool = True) -> TurnPlan:
        async with self._lock:
            now = datetime.now(timezone.utc)
            self._cleanup_expired(now)
            
            key = self._get_session_key(chat_id, user_id)
            if key not in self._sessions:
                self._sessions[key] = ConversationSession(chat_id=chat_id, user_id=user_id)
                
            session = self._sessions[key]
            
            # --- 1. Identify explicit targeting ---
            text_lower = text.lower()
            explicit_target = None
            selected_bots = []
            reason = "general_fallback"
            resolved_intent = "unknown"
            reference_type = None
            normalized_question = None
            
            # Mention dono
            if "dono" in text_lower or "both" in text_lower or ("niyati" in text_lower and "palak" in text_lower):
                explicit_target = "both"
            elif reply_to_bot_name == 'niyati' or f"@{Config.NIYATI_BOT_USERNAME.lower()}" in text_lower or bool(re.search(r'\b(niyati)\b', text_lower)):
                explicit_target = "niyati"
            elif reply_to_bot_name == 'palak' or f"@{Config.PALAK_BOT_USERNAME.lower()}" in text_lower or bool(re.search(r'\b(palak|palakdevabot)\b', text_lower)):
                explicit_target = "palak"
                
            # --- 2. Correction Handling ---
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
                logger.info(f"[Director] switched_to={explicit_target} reason=user_correction")
                
            # --- 3. Follow-up & Coreference Resolution ---
            short_continuations = ["ku", "kyu", "why", "kaise", "how", "fir", "then", "acha", "sach", "kon", "kab", "or batao", "matlab", "really", "achha"]
            is_short = text_lower.strip(' ?!') in short_continuations or len(text_lower.split()) <= 2
            
            if is_short and session.active_bot and not explicit_target:
                explicit_target = session.active_bot
                if text_lower.strip(' ?!') in ["ku", "kyu", "why"]:
                    resolved_intent = "ASK_REASON"
                elif text_lower.strip(' ?!') in ["matlab", "kaise"]:
                    resolved_intent = "ASK_CLARIFICATION"
                else:
                    resolved_intent = "CONTINUE_TOPIC"
                    
                reason = "short_followup:last_speaker"
                logger.info(f"[Director] active_bot={explicit_target} reason={reason}")

            # --- 4. Topic/Entity ownership ---
            entity_owner = None
            if not explicit_target:
                if bool(re.search(r'\b(arjun|mochi)\b', text_lower)):
                    entity_owner = "niyati"
                elif bool(re.search(r'\b(bruno|palakcreates)\b', text_lower)):
                    entity_owner = "palak"
                elif "delhi" in text_lower and any(w in text_lower for w in ["kaha", "kahan", "rehti", "city", "se ho"]):
                    entity_owner = "niyati"
                elif "mumbai" in text_lower and any(w in text_lower for w in ["kaha", "kahan", "rehti", "city", "se ho"]):
                    entity_owner = "palak"

            # --- 5. Determine Selection ---
            if explicit_target == "both":
                selected_bots = ["niyati", "palak"]
                reason = "explicit_both"
            elif explicit_target:
                selected_bots = [explicit_target]
                reason = reason if reason != "general_fallback" else "explicit_target"
            elif entity_owner:
                selected_bots = [entity_owner]
                reason = f"entity_owner:{entity_owner}"
            elif session.active_bot:
                selected_bots = [session.active_bot]
                reason = "active_bot_continuation"
            else:
                # Deterministic fallback
                seed_str = f"{chat_id}:{message_id}"
                seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
                rng = random.Random(seed_int)
                roll = rng.random()
                selected_bots = ['niyati'] if roll < 0.5 else ['palak']
                reason = "deterministic_fallback"
                
            # --- 6. Update Session ---
            # If both are selected, we might clear active_bot or keep it. Let's set it to None for 'both'
            if len(selected_bots) == 1:
                session.active_bot = selected_bots[0]
                session.active_since = session.active_since or now
            else:
                session.active_bot = None
                
            if "?" in text or any(w in text_lower.split() for w in ["kya", "kaise", "kyu", "kon", "kab"]):
                session.pending_question = normalized_question or text
            
            session.last_human_message_id = message_id
            session.recent_turns += 1
            session.expires_at = now + timedelta(minutes=10)
            
            plan = TurnPlan(
                chat_id=chat_id,
                human_user_id=user_id,
                human_message_id=message_id,
                selected_bots=selected_bots,
                primary_bot=selected_bots[0] if selected_bots else None,
                explicit_target=explicit_target,
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
            return plan

    async def register_bot_response(self, chat_id: int, user_id: int, bot_name: str, message_id: int, claim_type: Optional[str] = None):
        async with self._lock:
            key = self._get_session_key(chat_id, user_id)
            if key in self._sessions:
                session = self._sessions[key]
                session.last_bot_name = bot_name
                session.last_bot_message_id = message_id
                if claim_type:
                    session.last_topic = claim_type

# Singleton
director = ConversationDirector()
