"""
╔══════════════════════════════════════════════════════╗
║              AI ENGINE                                ║
║   Hybrid AI: OpenAI → Groq → Gemini (Auto-Failover)  ║
║   Bot-Aware: Each bot gets its own engine instance    ║
╚══════════════════════════════════════════════════════╝
"""

import asyncio
import random
from typing import List, Dict, Optional

import httpx
from openai import AsyncOpenAI
from collections import deque
from difflib import SequenceMatcher

from config import Config, logger
from characters import get_character
from memory import get_memory
from utils import Mood, TimeAware
from datetime import datetime, timezone
from datetime import datetime, timezone


BANNED_GENERIC_PHRASES = [
    "acha that's good",
    "main sunne ke liye hu",
    "bas college ka kaam",
    "classes attend karke notes",
    "painting karne ki soch rahi",
    "ghar pe araam kar rahi",
    "honestly abhi kuch clear nahi",
]

class AIEngine:
    """
    Hybrid AI engine with multi-provider failover.
    Bot-aware: uses character cards to build prompts.
    Each bot should have its own instance to isolate key rotation state.
    """

    def __init__(self):
        self.openai_keys = getattr(Config, 'API_KEYS_LIST', [])
        self.groq_keys = Config.GROQ_API_KEYS_LIST
        self.gemini_keys = Config.GEMINI_API_KEYS_LIST

        # Priority order: Groq (fast & free) → Gemini → OpenAI (fallback)
        self.all_keys = []
        for k in self.groq_keys:
            self.all_keys.append({"type": "groq", "key": k})
        for k in self.gemini_keys:
            self.all_keys.append({"type": "gemini", "key": k})
        for k in self.openai_keys:
            self.all_keys.append({"type": "openai", "key": k})

        self.current_index = 0
        self.client = None
        self._initialize_client()
        logger.info(f"AI Engine: {len(self.groq_keys)} Groq, {len(self.gemini_keys)} Gemini, {len(self.openai_keys)} OpenAI keys")

    def _initialize_client(self):
        """Initialize Client based on Key Type"""
        if not self.all_keys:
            logger.error("No API Keys found!")
            return

        current = self.all_keys[self.current_index]

        if current['type'] == "openai":
            self.client = AsyncOpenAI(api_key=current['key'])
        elif current['type'] == "groq":
            self.client = AsyncOpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=current['key']
            )

        masked = current['key'][:8] + "..." + current['key'][-4:]
        logger.info(f"Current AI: {current['type'].upper()} | Key: {masked}")

    def _rotate(self):
        """Switch to next key when one fails"""
        if len(self.all_keys) <= 1:
            return False
        self.current_index = (self.current_index + 1) % len(self.all_keys)
        self._initialize_client()
        return True

    async def _call_gpt(self, messages: List[Dict], max_tokens: int = 350,
                         temp: float = 0.85) -> Optional[str]:
        """Unified caller for OpenAI, Groq, and Gemini"""
        attempts = len(self.all_keys) if self.all_keys else 1

        for attempt_num in range(attempts):
            if not self.all_keys:
                break

            curr = self.all_keys[self.current_index]
            try:
                # OpenAI or Groq
                if curr['type'] in ["openai", "groq"]:
                    model_name = "gpt-4o-mini" if curr['type'] == "openai" else Config.GROQ_MODEL

                    params = {
                        "model": model_name,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temp,
                    }
                    if curr['type'] == "openai":
                        params["presence_penalty"] = 0.6

                    response = await self.client.chat.completions.create(**params)
                    result = response.choices[0].message.content

                    if result:
                        result = result.strip()
                        logger.debug(f"AI ({curr['type']}): {result[:80]}...")
                        return result
                    else:
                        logger.warning(f"Empty response from {curr['type']}")
                        self._rotate()
                        continue

                # Gemini
                elif curr['type'] == "gemini":
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{Config.GEMINI_MODEL}:generateContent?key={curr['key']}"

                    system_text = ""
                    contents = []
                    for m in messages:
                        if m['role'] == 'system':
                            system_text = m['content']
                        else:
                            role = "model" if m['role'] == "assistant" else "user"
                            contents.append({"role": role, "parts": [{"text": m['content']}]})

                    payload = {
                        "contents": contents,
                        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temp}
                    }
                    if system_text:
                        payload["systemInstruction"] = {"parts": [{"text": system_text}]}

                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(url, json=payload)
                        if resp.status_code == 200:
                            data = resp.json()
                            result = data['candidates'][0]['content']['parts'][0]['text'].strip()
                            logger.debug(f"AI (gemini): {result[:80]}...")
                            return result
                        else:
                            raise Exception(f"Gemini {resp.status_code}: {resp.text[:100]}")

            except Exception as e:
                logger.warning(f"{curr['type'].upper()} Failed (attempt {attempt_num+1}): {str(e)[:80]}. Rotating...")
                await asyncio.sleep(0.5)
                if not self._rotate():
                    break

        logger.error("ALL AI providers failed!")
        return None


    # ========== PUBLIC API ==========

    async def generate_response(self, bot_name: str, user_id: int, chat_id: int,
                                 user_message: str, user_name: str,
                                 is_group: bool = False,
                                 reply_to_user: str = None,
                                 psychological_context: str = None,
                                 recent_responses: List[str] = None,
                                 active_claims: Dict = None) -> List[str]:
        """
        Generate AI response for a bot.
        """
        # 1. Get character
        character = get_character(bot_name)

        # 2. Get mood & time
        mood = Mood.get_random_mood()
        time_period = TimeAware.get_time_period()

        # 3. Get memory context
        memory = get_memory(bot_name)
        context_msgs = await memory.build_ai_context(
            user_id=user_id,
            user_name=user_name,
            chat_id=chat_id,
            is_group=is_group,
            reply_to_user=reply_to_user
        )

        # 4. Build group context string for system prompt
        group_context_str = None
        if is_group and context_msgs:
            group_context_str = "\n".join(
                msg['content'] for msg in context_msgs[-8:]
            )
            


        # 9. Build system prompt using character's prompt builder
        system_prompt = character['build_system_prompt'](
            mood=mood,
            time_period=time_period,
            user_name=user_name,
            is_group=is_group,
            group_context=group_context_str,
            psychological_context=psychological_context
        )
        
        other_bot = 'niyati' if bot_name == 'palak' else 'palak'
        system_prompt += f"\n\nYou are {bot_name.upper()}.\nRespond only as {bot_name.upper()}.\nNever reproduce role labels.\nNever answer a message assigned to {other_bot.upper()}.\nNever use 'hum dono', 'humein', or 'ja rahe hain' to speak for both."

        # 6. Build messages for AI
        messages = [{"role": "system", "content": system_prompt}]

        if not is_group and context_msgs:
            for msg in context_msgs[-5:]:
                messages.append({
                    "role": msg.get('role', 'user'),
                    "content": msg.get('content', '')
                })

        if is_group:
            messages.append({"role": "user", "content": f"[{user_name}]: {user_message}"})
        else:
            messages.append({"role": "user", "content": user_message})

        # 7. Call AI (with repetition guard and strict validation)
        max_retries = 2
        reply = None
        for attempt in range(max_retries + 1):
            reply = await self._call_gpt(messages)
            if not reply or reply.upper() == "IGNORE":
                break
                
            invalid = False
            reply_lower = reply.lower()
            
            # Check banned phrases
            if any(p in reply_lower for p in BANNED_GENERIC_PHRASES):
                invalid = True
                
            # Check length (reject excessively long messages)
            if len(reply.split('\n')) > 4 or len(reply) > 300:
                invalid = True
                
            # Check cross-bot speaking and plural identity leak
            if f"{other_bot.capitalize()}:" in reply or f"[{other_bot.capitalize()}]" in reply:
                invalid = True
                
            if "hum dono" in reply_lower or "humein" in reply_lower or "ja rahe hain" in reply_lower:
                invalid = True
                
            # Repeated filler phrases
            if any(p in reply_lower for p in ["chill karo", "gussa kyu", "gussa kiyon", "maaf kar do"]):
                invalid = True
                
            # Repetition guard and Fingerprinting
            if is_group and recent_responses:
                for old_reply in recent_responses:
                    old_lower = old_reply.lower()
                    ratio = SequenceMatcher(None, reply_lower, old_lower).ratio()
                    if ratio > 0.75:
                        invalid = True
                        break
                    # Catch generic short repeats
                    if len(reply_lower) < 40 and (reply_lower in old_lower or old_lower in reply_lower):
                        invalid = True
                        break
            # Claim Consistency Validation
            if active_claims:
                for ctype, claim in active_claims.items():
                    # Reject direct negation of active claims
                    if ctype == "current_feeling" and claim.value == "sleepy":
                        if "neend nahi" in reply_lower or "bilkul sleepy nahi" in reply_lower:
                            invalid = True
                            logger.warning(f"[{bot_name}] Contradicts claim: directly negated feeling sleepy")
                            break
                        
                        # If user asked reason (why are you sleepy?), AI must answer about sleepy, not just switch to bored
                        if "bored" in reply_lower or "bore" in reply_lower:
                            if "sleep" not in reply_lower and "neend" not in reply_lower and "soyi" not in reply_lower and "sone" not in reply_lower and "thak" not in reply_lower:
                                invalid = True
                                logger.warning(f"[{bot_name}] Contradicts claim: replaced sleepy with bored without explaining sleepy")
                                break
                                
            if invalid:
                logger.warning(f"[{bot_name}] Response rejected. Retrying... (Attempt {attempt+1}/{max_retries})")
                reply = None
                # Add a random variation instruction to force a different response
                messages.append({"role": "system", "content": "The previous response was invalid (either too generic, too long, used wrong character, or repetitive). Be more natural, very short, and follow the rules."})
                continue
            
            # If we reached here, valid!
            break

        if not reply:
            return character.get('error_responses', ["network issue", "thodi der mein try karo?"])

        if reply.upper() == "IGNORE":
            return []

        # 8. Parse multi-message response
        parts = reply.split('|||') if '|||' in reply else [reply]
        responses = [p.strip() for p in parts if p.strip()][:4]

        # 9. Save to memory
        if not is_group:
            await memory.save_private_message(user_id, 'user', user_message)
            await memory.save_private_message(user_id, 'assistant', ' '.join(responses))

        if is_group:
            memory.set_last_reply_to(chat_id, user_id)

        return responses

    async def generate_fallback_response(self, bot_name: str, user_id: int, chat_id: int,
                                          user_message: str, user_name: str,
                                          is_group: bool = False,
                                          fallback_instruction: str = None) -> List[str]:
        """
        Constrained single-attempt fallback generation used when normal
        generation produces 0 valid candidates.
        """
        character = get_character(bot_name)
        mood = Mood.get_random_mood()
        time_period = TimeAware.get_time_period()
        memory = get_memory(bot_name)
        context_msgs = await memory.build_ai_context(
            user_id=user_id, user_name=user_name, chat_id=chat_id,
            is_group=is_group, reply_to_user=None
        )
        group_context_str = None
        if is_group and context_msgs:
            group_context_str = "\n".join(msg['content'] for msg in context_msgs[-6:])
        system_prompt = character['build_system_prompt'](
            mood=mood, time_period=time_period, user_name=user_name,
            is_group=is_group, group_context=group_context_str, psychological_context=None
        )
        other_bot = 'niyati' if bot_name == 'palak' else 'palak'
        constraint = (
            fallback_instruction or
            "Answer the user's question in one short natural Hinglish sentence. "
            "Speak only for yourself. Do not change the topic."
        )
        system_prompt += f"\n\nYou are {bot_name.upper()}.\n{constraint}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"[{user_name}]: {user_message}" if is_group else user_message},
        ]
        reply = await self._call_gpt(messages, max_tokens=120, temp=0.7)
        if not reply or reply.upper() == "IGNORE":
            return []
        return [reply.strip()]

    async def generate_shayari(self, mood: str = "neutral") -> str:
        """Generate a random shayari"""
        prompt = f"Write a 2 line heart-touching Hinglish shayari for {mood} mood."
        res = await self._call_gpt([{"role": "user", "content": prompt}], max_tokens=100, temp=0.9)

    async def generate_geeta_quote(self) -> str:
        """Generate a Bhagavad Gita quote"""
        prompt = "Give a short Bhagavad Gita quote with Hinglish meaning. Start with 🙏"
        res = await self._call_gpt([{"role": "user", "content": prompt}], max_tokens=150)
        return res if res else "🙏 Karm karo phal ki chinta mat karo."

    async def get_random_bonus(self) -> Optional[str]:
        """Get random bonus content (shayari/meme)"""
        rand = random.random()
        if rand < Config.RANDOM_SHAYARI_CHANCE:
            return await self.generate_shayari()
        elif rand < Config.RANDOM_SHAYARI_CHANCE + Config.RANDOM_MEME_CHANCE:
            return random.choice([
                "Life is pain 🥲", "Moye Moye 💃", "Us moment 🤝",
                "Kya logic hai? 🤦‍♀️", "Main toh vibe kar raha 😎"
            ])
        return None


# ============================================================================
# PER-BOT ENGINE REGISTRY
# ============================================================================

_engines: Dict[str, AIEngine] = {}


def get_ai_engine(bot_name: str) -> AIEngine:
    """
    Get or create a persistent AIEngine instance for a specific bot.
    Each bot gets its own engine with independent key rotation state.
    """
    bot_name = bot_name.lower()
    if bot_name not in _engines:
        _engines[bot_name] = AIEngine()
        logger.info(f"AIEngine created for {bot_name}")
    return _engines[bot_name]
