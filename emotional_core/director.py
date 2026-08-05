import re
import random
import hashlib
from typing import Dict, Tuple, List, Optional
from datetime import datetime, timezone, timedelta
import asyncio
from config import logger, Config

from .models import TurnPlan, ConversationSession, SHARED_WORLD

# ── Ambiguous-referent tokens ────────────────────────────────────────────────
_AMBIGUOUS_REFS = re.compile(
    r'\b(wo|woh|uski|tumhari\s+friend|tumhari\s+dost|wo\s+ladki|she|her)\b',
    re.IGNORECASE
)

# ── Relation-reference tokens ────────────────────────────────────────────────
_RELATION_REFS = {
    "friend": ["friend", "dost"],
    "sister": ["sister", "behen"],
}

# ── Character name patterns ───────────────────────────────────────────────────
_NIYATI_PAT = re.compile(r'\b(niyati)\b', re.IGNORECASE)
_PALAK_PAT  = re.compile(r'\b(palak|palakdevabot)\b', re.IGNORECASE)

# ── Shared-world contradiction patterns ──────────────────────────────────────
_FRIEND_DENIAL = re.compile(
    r'\b(nahi\s+(meri|teri)\s+friend|wo\s+meri\s+friend\s+nahi|not\s+my\s+friend'
    r'|koi\s+dost\s+nahi|dost\s+nahi\s+hai)\b',
    re.IGNORECASE
)


def _both_turn_prompt(bot_name: str, other_bot: str, original_msg: str) -> str:
    return (
        "The user is asking both characters. Answer ONLY for "
        + bot_name.capitalize()
        + " and describe only your own habits/feelings/opinions."
        + " Do NOT speak for " + other_bot.capitalize() + "."
        + " Do NOT use hum, humein, hum dono, or ja rahe hain."
        + " User question: " + original_msg
    )


class ConversationDirector:
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
        cutoff = now - timedelta(minutes=20)
        expired_plans = [k for k, p in self._turn_plans.items() if p.created_at < cutoff]
        for k in expired_plans:
            del self._turn_plans[k]
        if len(self._turn_plans) > 1000:
            sorted_plans = sorted(self._turn_plans.items(), key=lambda item: item[1].created_at)
            for k, p in sorted_plans[:len(self._turn_plans)-1000]:
                del self._turn_plans[k]

    def clear(self):
        self._sessions.clear()
        self._turn_plans.clear()

    @staticmethod
    def _detect_ambiguous_referent(text: str) -> bool:
        return bool(_AMBIGUOUS_REFS.search(text))

    @staticmethod
    def _resolve_clarification_entity(text: str) -> Optional[str]:
        stripped = text.strip().lower().rstrip('?! ')
        if stripped == "niyati":
            return "niyati"
        if stripped in ("palak", "palakdevabot"):
            return "palak"
        return None

    @staticmethod
    def _detect_relation_reference(text_lower: str) -> Optional[str]:
        for rel, keywords in _RELATION_REFS.items():
            if any(kw in text_lower for kw in keywords):
                return rel
        return None

    @staticmethod
    def _is_explicit_speaker_switch(text_lower: str) -> Optional[str]:
        if re.search(r'\bniyati\s+(tum\s+batao|bolo|batao|answer\s+karo)\b', text_lower):
            return "niyati"
        if re.search(r'\bpalak\s+(tum\s+batao|bolo|batao|answer\s+karo)\b', text_lower):
            return "palak"
        if re.search(r'\bpalak\s+se\s+(puch|baat|bol)\b', text_lower):
            return "palak"
        if re.search(r'\bniyati\s+se\s+(puch|baat|bol)\b', text_lower):
            return "niyati"
        return None

    def _validate_world_facts(self, bot_name: str, response_text: str, resolved_entity: Optional[str]) -> bool:
        text_lower = response_text.lower()
        if resolved_entity and SHARED_WORLD.is_friend_of_bot(resolved_entity, bot_name):
            if _FRIEND_DENIAL.search(text_lower):
                logger.warning("[%s] SharedWorld violation: friend-denial about %s", bot_name, resolved_entity)
                return True
        return False

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
            selected_bots = ()
            reason = "general_fallback"
            resolved_intent = "unknown"
            reference_type = None
            normalized_question = None
            is_both_turn = False
            bot_prompts = ()

            # 1. CLARIFY_REFERENT (highest priority after plan cache)
            if session.clarification_expected and session.clarification_target_bot:
                clarify_entity = self._resolve_clarification_entity(text)
                if clarify_entity:
                    resolved_intent = "CLARIFY_REFERENT"
                    explicit_target = session.clarification_target_bot
                    orig_q = session.pending_ambiguous_question or text
                    normalized_question = _AMBIGUOUS_REFS.sub(
                        clarify_entity.capitalize(), orig_q
                    ).strip()
                    if not normalized_question.endswith("?"):
                        normalized_question += "?"
                    reason = "clarify_referent"
                    session.last_person_entity = clarify_entity
                    session.clarification_expected = False
                    session.clarification_target_bot = None
                    logger.info(
                        "[Reference] clarification entity=%s original_question=%r normalized=%r",
                        clarify_entity, orig_q, normalized_question
                    )
                    logger.info("[Director] intent=CLARIFY_REFERENT target=%s", explicit_target)
                    selected_bots = (explicit_target,)
                    session.last_human_message_id = message_id
                    sess_ts = session.active_since.timestamp() if session.active_since else now.timestamp()
                    plan = TurnPlan(
                        chat_id=chat_id,
                        human_user_id=user_id,
                        human_message_id=message_id,
                        selected_bots=selected_bots,
                        primary_bot=explicit_target,
                        explicit_target=explicit_target,
                        active_bot=session.active_bot,
                        referenced_bot=clarify_entity,
                        referenced_message_id=session.last_bot_message_id,
                        active_topic=session.last_topic,
                        resolved_intent=resolved_intent,
                        reference_type="discourse_referent",
                        normalized_question=normalized_question,
                        reason=reason,
                        conversation_session_id=str(chat_id) + "_" + str(user_id) + "_" + str(sess_ts),
                    )
                    self._turn_plans[plan_key] = plan
                    return plan

            # 2. Explicit speaker switch
            speaker_switch = self._is_explicit_speaker_switch(text_lower)

            # 3. Standard routing precedence
            if reply_to_bot_name:
                explicit_target = reply_to_bot_name
                reason = "telegram_reply"
            elif ("@" + Config.NIYATI_BOT_USERNAME.lower()) in text_lower:
                explicit_target = "niyati"
                reason = "explicit_mention"
            elif ("@" + Config.PALAK_BOT_USERNAME.lower()) in text_lower:
                explicit_target = "palak"
                reason = "explicit_mention"
            elif speaker_switch:
                explicit_target = speaker_switch
                resolved_intent = "SWITCH_SPEAKER"
                reason = "speaker_switch"
                logger.info("[Director] intent=SWITCH_SPEAKER target=%s", explicit_target)
            elif "dono" in text_lower or "both" in text_lower or (_NIYATI_PAT.search(text) and _PALAK_PAT.search(text)):
                explicit_target = "both"
                reason = "explicit_both"
            elif _NIYATI_PAT.search(text) and not _PALAK_PAT.search(text):
                if session.active_bot == "palak":
                    resolved_intent = "ASK_ABOUT_OTHER_CHARACTER"
                    explicit_target = "palak"
                    reason = "ask_about_other:niyati"
                    session.last_person_entity = "niyati"
                    logger.info("[Director] intent=ASK_ABOUT_OTHER_CHARACTER about=niyati via=palak")
                else:
                    explicit_target = "niyati"
                    reason = "explicit_name"
            elif _PALAK_PAT.search(text) and not _NIYATI_PAT.search(text):
                if session.active_bot == "niyati":
                    resolved_intent = "ASK_ABOUT_OTHER_CHARACTER"
                    explicit_target = "niyati"
                    reason = "ask_about_other:palak"
                    session.last_person_entity = "palak"
                    logger.info("[Director] intent=ASK_ABOUT_OTHER_CHARACTER about=palak via=niyati")
                else:
                    explicit_target = "palak"
                    reason = "explicit_name"
            elif bool(re.search(r'\b(arjun|mochi)\b', text_lower)) or ("delhi" in text_lower and any(w in text_lower for w in ["kaha", "kahan", "rehti", "city", "se ho"])):
                explicit_target = "niyati"
                reason = "entity_owner:niyati"
            elif bool(re.search(r'\b(bruno|palakcreates)\b', text_lower)) or ("mumbai" in text_lower and any(w in text_lower for w in ["kaha", "kahan", "rehti", "city", "se ho"])):
                explicit_target = "palak"
                reason = "entity_owner:palak"
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
            elif session.active_bot:
                explicit_target = session.active_bot
                reason = "active_bot_continuation"
            else:
                seed_str = str(chat_id) + ":" + str(message_id)
                seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
                rng = random.Random(seed_int)
                roll = rng.random()
                explicit_target = "niyati" if roll < 0.5 else "palak"
                reason = "deterministic_fallback"

            # 4. Ambiguous referent detection
            has_ambiguous = self._detect_ambiguous_referent(text)
            relation_ref = self._detect_relation_reference(text_lower)
            if relation_ref:
                session.last_relation_reference = relation_ref
            if has_ambiguous and explicit_target and explicit_target != "both":
                session.clarification_expected = True
                session.clarification_target_bot = explicit_target
                session.pending_ambiguous_question = text
                resolved_intent = "AMBIGUOUS_REFERENT"
                logger.info(
                    "[Reference] ambiguous referent in %r, expecting clarification for bot=%s",
                    text, explicit_target
                )

            # 5. Correction handling
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
                logger.info("[Director] switched_to=%s reason=user_correction", explicit_target)

            # 6. Determine selection + both-turn per-bot prompts
            if explicit_target == "both":
                selected_bots = ("niyati", "palak")
                is_both_turn = True
                niyati_prompt = _both_turn_prompt("niyati", "palak", text)
                palak_prompt  = _both_turn_prompt("palak", "niyati", text)
                bot_prompts = (("niyati", niyati_prompt), ("palak", palak_prompt))
                logger.info("[BothTurn] created child_plan bot=niyati")
                logger.info("[BothTurn] created child_plan bot=palak")
            else:
                selected_bots = (explicit_target,)

            # 7. Pre-update session
            if "?" in text or any(w in text_lower.split() for w in ["kya", "kaise", "kyu", "kon", "kab"]):
                if not is_correction:
                    session.pending_question = text
                    if not normalized_question:
                        normalized_question = text

            session.last_human_message_id = message_id
            sess_ts = session.active_since.timestamp() if session.active_since else now.timestamp()
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
                conversation_session_id=str(chat_id) + "_" + str(user_id) + "_" + str(sess_ts),
                is_both_turn=is_both_turn,
                bot_prompts=bot_prompts,
            )
            self._turn_plans[plan_key] = plan
            return plan

    async def record_turn_outcome(self, chat_id: int, human_user_id: int, human_message_id: int,
                                  conversation_session_id: str, responding_bot: str,
                                  outcome, sent_bot_message_ids: tuple,
                                  response_text: str, claim_type: Optional[str] = None) -> bool:
        async with self._lock:
            plan_key = (chat_id, human_message_id)
            if plan_key not in self._turn_plans:
                return False
            plan = self._turn_plans[plan_key]
            if responding_bot not in plan.selected_bots:
                return False
            if plan.conversation_session_id != conversation_session_id:
                return False
            key = self._get_session_key(chat_id, human_user_id)
            if key not in self._sessions:
                return False
            session = self._sessions[key]
            if session.last_human_message_id and human_message_id < session.last_human_message_id:
                return False
            outcome_key = (human_message_id, responding_bot)
            if outcome_key in session.processed_outcomes:
                return False
            session.processed_outcomes.add(outcome_key)
            if outcome.name == "SUCCESS":
                now = datetime.now(timezone.utc)
                if not plan.is_both_turn:
                    session.active_bot = responding_bot
                else:
                    if not session.active_bot or session.active_bot not in ("niyati", "palak"):
                        session.active_bot = responding_bot
                session.active_since = session.active_since or now
                session.last_bot_name = responding_bot
                if sent_bot_message_ids:
                    session.last_bot_message_id = sent_bot_message_ids[0]
                session.recent_turns += 1
                session.expires_at = now + timedelta(minutes=20)
                if claim_type:
                    session.last_topic = claim_type
            return True

    def check_world_facts_violation(self, bot_name: str, response_text: str,
                                    resolved_entity: Optional[str]) -> bool:
        return self._validate_world_facts(bot_name, response_text, resolved_entity)


# Singleton
director = ConversationDirector()
