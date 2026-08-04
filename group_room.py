"""
╔══════════════════════════════════════════════════════╗
║           GROUP ROOM MANAGER                          ║
║   Shared state, deduplication, turn coordination      ║
╚══════════════════════════════════════════════════════╝
"""

import asyncio
import random
import hashlib
from typing import Dict, Optional, Set, List, Tuple
from collections import deque
from datetime import datetime, timezone, timedelta
from config import Config, logger


class GroupRoomState:
    def __init__(self, chat_id: int):
        self.chat_id: int = chat_id
        self.title: str = ""
        self.niyati_present: Optional[bool] = None
        self.palak_present: Optional[bool] = None
        
        # Session state
        self.active_human_user_id: Optional[int] = None
        self.last_human_message_at: Optional[datetime] = None
        self.active_until: Optional[datetime] = None
        self.conversation_depth: int = 0
        self.last_responder: Optional[str] = None
        
        # Per-message plans: {message_id: plan_list}
        self._plans: Dict[int, List[str]] = {}
        
        # Per-trigger bot-to-bot tracking: {trigger_message_id: count}
        self._trigger_bot_replies: Dict[int, int] = {}
        self._trigger_message_id: Optional[int] = None
        self.consecutive_bot_replies: int = 0
        
        # Track which bots already sent a response for which trigger
        # (bot_name, trigger_message_id) → True
        self._bot_responded: Set[Tuple[str, int]] = set()
        
        # Deduplication state
        self.processed_by_bot: Set[Tuple[str, int]] = set()  # (bot_name, message_id)
        self.transcript_keys: Set[Tuple[int, int]] = set()   # (message_id, sender_id)
        
        # Shared memory
        self.transcript: deque = deque(maxlen=Config.MAX_GROUP_MESSAGES if hasattr(Config, 'MAX_GROUP_MESSAGES') else 50)
        self.lock = asyncio.Lock()
        
    def has_active_human_session(self) -> bool:
        if not self.active_until:
            return False
        return datetime.now(timezone.utc) < self.active_until

    def update_presence(self, bot_name: str, is_present: bool):
        if bot_name == 'niyati':
            self.niyati_present = is_present
        elif bot_name == 'palak':
            self.palak_present = is_present

    def is_partner_present(self, my_bot_name: str) -> Optional[bool]:
        if my_bot_name == 'niyati':
            return self.palak_present
        elif my_bot_name == 'palak':
            return self.niyati_present
        return None

    def get_plan(self, message_id: int) -> Optional[List[str]]:
        return self._plans.get(message_id)

    def get_bot_replies_for_trigger(self) -> int:
        if self._trigger_message_id is None:
            return 0
        return self._trigger_bot_replies.get(self._trigger_message_id, 0)

    def increment_bot_replies(self):
        if self._trigger_message_id is not None:
            self._trigger_bot_replies[self._trigger_message_id] = \
                self._trigger_bot_replies.get(self._trigger_message_id, 0) + 1

    def _cleanup_old_plans(self):
        """Keep only recent plans to prevent memory leak."""
        if len(self._plans) > 200:
            keys = sorted(self._plans.keys())
            for k in keys[:100]:
                del self._plans[k]
        if len(self._trigger_bot_replies) > 200:
            keys = sorted(self._trigger_bot_replies.keys())
            for k in keys[:100]:
                del self._trigger_bot_replies[k]
        if len(self._bot_responded) > 500:
            self._bot_responded = set(list(self._bot_responded)[-250:])


class GroupRoomManager:
    def __init__(self):
        self._rooms: Dict[int, GroupRoomState] = {}
        self._global_lock = asyncio.Lock()
        self._bot_ids: Dict[str, int] = {}
        
    def register_bot(self, bot_name: str, bot_id: int):
        self._bot_ids[bot_name] = bot_id
        
    def get_bot_id(self, bot_name: str) -> Optional[int]:
        return self._bot_ids.get(bot_name)

    def get_partner_name(self, bot_name: str) -> Optional[str]:
        """Get the partner bot's internal name."""
        if bot_name == 'niyati':
            return 'palak'
        elif bot_name == 'palak':
            return 'niyati'
        return None
        
    async def update_presence(self, chat_id: int, bot_name: str, is_present: bool):
        room = await self.get_room(chat_id)
        room.update_presence(bot_name, is_present)

    async def get_room(self, chat_id: int) -> GroupRoomState:
        async with self._global_lock:
            if chat_id not in self._rooms:
                self._rooms[chat_id] = GroupRoomState(chat_id)
            return self._rooms[chat_id]

    async def process_human_message(self, bot_name: str, chat_id: int, message_id: int, 
                                    sender_id: int, sender_name: str, text: str,
                                    reply_to_bot_name: str = None) -> Tuple[bool, List[str]]:
        """
        Process an incoming human message.
        
        Returns (should_proceed, planned_responders).
        - should_proceed=False means this bot already processed this message.
        - The plan is created once per message_id by the first bot to arrive.
        - The second bot sees the same plan without recalculating or double-resetting.
        """
        room = await self.get_room(chat_id)
        
        async with room.lock:
            # 1. Handler Processing Dedupe
            bot_msg_key = (bot_name, message_id)
            if bot_msg_key in room.processed_by_bot:
                plan = room.get_plan(message_id) or []
                return False, plan
            room.processed_by_bot.add(bot_msg_key)
            
            # 2. Check if plan already exists for this message_id (set by the other bot)
            existing_plan = room.get_plan(message_id)
            if existing_plan is not None:
                # Plan already computed by the other bot — just use it, don't reset counters
                return True, existing_plan

            # 3. First bot to see this message: create plan and update session
            plan = self._decide_responders(room, message_id, sender_id, text, reply_to_bot_name)
            room._plans[message_id] = plan
            
            logger.info(f"[Coordinator] Message {message_id} -> {plan}")
            
            # 4. Transcript Dedupe
            transcript_key = (message_id, sender_id)
            if transcript_key not in room.transcript_keys:
                room.transcript_keys.add(transcript_key)
                room.transcript.append({
                    'message_id': message_id,
                    'sender_name': sender_name,
                    'sender_id': sender_id,
                    'content': text,
                    'is_bot': False,
                    'bot_name': None,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            
            # 5. Update Session State — only the first bot does this
            now = datetime.now(timezone.utc)
            room.active_human_user_id = sender_id
            room._trigger_message_id = message_id
            room.last_human_message_at = now
            room.active_until = now + timedelta(seconds=75)
            room.conversation_depth += 1
            
            # 6. Reset per-trigger counters
            room._trigger_bot_replies[message_id] = 0
            room.consecutive_bot_replies = 0
            room.last_responder = None
            
            # 7. Cleanup old data
            if len(room.processed_by_bot) > 1000:
                room.processed_by_bot = set(list(room.processed_by_bot)[-500:])
            if len(room.transcript_keys) > 1000:
                room.transcript_keys = set(list(room.transcript_keys)[-500:])
            room._cleanup_old_plans()
                
            return True, plan

    async def add_bot_message(self, bot_name: str, chat_id: int, message_id: int, 
                              bot_display_name: str, text: str):
        """
        Add a bot's response to the transcript and count it.
        Bots DO NOT open or refresh human sessions.
        """
        room = await self.get_room(chat_id)
        
        async with room.lock:
            if not room.has_active_human_session():
                return
                
            transcript_key = (message_id, 0)
            if transcript_key not in room.transcript_keys:
                room.transcript_keys.add(transcript_key)
                room.transcript.append({
                    'message_id': message_id,
                    'sender_name': bot_display_name,
                    'sender_id': 0,
                    'content': text,
                    'is_bot': True,
                    'bot_name': bot_name,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            
            # Count this bot response toward the per-trigger maximum
            room.increment_bot_replies()
            room.last_responder = bot_name
            
            # Track that this bot responded for the current trigger
            if room._trigger_message_id is not None:
                room._bot_responded.add((bot_name, room._trigger_message_id))

    async def process_partner_message(self, bot_name: str, chat_id: int, message_id: int, 
                                      partner_id: int, partner_name: str, text: str) -> Tuple[bool, List[str]]:
        """
        Process a message sent by the partner bot.
        Prevents bot loops via depth limits and checks if this bot was
        already planned to respond through the human-message path.
        """
        room = await self.get_room(chat_id)
        
        async with room.lock:
            # 1. Deduplicate
            bot_msg_key = (bot_name, message_id)
            if bot_msg_key in room.processed_by_bot:
                return False, []
            room.processed_by_bot.add(bot_msg_key)
            
            # 2. If this bot already responded to the current trigger via the
            #    human-message planned path, don't also respond via partner reaction.
            if room._trigger_message_id is not None:
                if (bot_name, room._trigger_message_id) in room._bot_responded:
                    logger.debug(f"[{bot_name}] Already responded for trigger {room._trigger_message_id}, skipping partner reaction")
                    return False, []
            
            # 3. Session active?
            if not room.has_active_human_session():
                logger.debug(f"[{bot_name}] Ignored partner bot message - no active human session")
                return False, []
                
            # 4. Depth limits
            if room.get_bot_replies_for_trigger() >= Config.MAX_BOT_REPLIES_PER_HUMAN_MESSAGE:
                logger.debug(f"[{bot_name}] Max total bot replies reached")
                return False, []
                
            if room.consecutive_bot_replies >= Config.MAX_CONSECUTIVE_BOT_TO_BOT_REPLIES:
                logger.debug(f"[{bot_name}] Max consecutive bot replies reached")
                return False, []
                
            # 5. Determine if this bot should respond
            planned = self._decide_responders(room, message_id, partner_id, text)
            if bot_name not in planned:
                return False, planned
                
            # 6. Increment counters
            room.consecutive_bot_replies += 1
            
            return True, planned

    async def get_transcript(self, chat_id: int, limit: int = 15) -> List[Dict]:
        """Get the shared transcript for this room."""
        room = await self.get_room(chat_id)
        async with room.lock:
            return list(room.transcript)[-limit:]

    def _decide_responders(self, room: GroupRoomState, message_id: int, sender_id: int, 
                           text: str, reply_to_bot_name: str = None) -> List[str]:
        """
        Deterministic seeded random decision of who responds.
        Seed: chat_id:message_id:sender_id
        
        reply_to_bot_name: if the human is replying to a specific bot's message,
        that bot is guaranteed to respond.
        """
        # Single bot presence override
        if room.niyati_present is True and room.palak_present is False:
            return ['niyati']
        if room.palak_present is True and room.niyati_present is False:
            return ['palak']
            
        seed_str = f"{room.chat_id}:{message_id}:{sender_id}"
        seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
        rng = random.Random(seed_int)
        
        text_lower = text.lower()
        
        # Priority 0: Reply-to a specific bot
        if reply_to_bot_name == 'niyati':
            if rng.random() < Config.PROB_CHIP_IN:
                return ['niyati', 'palak']
            return ['niyati']
        if reply_to_bot_name == 'palak':
            if rng.random() < Config.PROB_CHIP_IN:
                return ['palak', 'niyati']
            return ['palak']
        
        # Priority 1: "dono" or mentioning both explicitly
        if "dono" in text_lower or ("niyati" in text_lower and "palak" in text_lower):
            res = ['niyati', 'palak']
            rng.shuffle(res)
            return res
            
        # Priority 2: Direct Mention
        niyati_mentioned = "niyati" in text_lower or f"@{Config.NIYATI_BOT_USERNAME.lower()}" in text_lower
        palak_mentioned = "palak" in text_lower or f"@{Config.PALAK_BOT_USERNAME.lower()}" in text_lower
        
        if niyati_mentioned:
            if rng.random() < Config.PROB_CHIP_IN:
                return ['niyati', 'palak']
            return ['niyati']
            
        if palak_mentioned:
            if rng.random() < Config.PROB_CHIP_IN:
                return ['palak', 'niyati']
            return ['palak']
            
        # Priority 3: General message distribution
        roll = rng.random()
        if roll < Config.PROB_NIYATI_ONLY:
            return ['niyati']
        elif roll < Config.PROB_NIYATI_ONLY + Config.PROB_PALAK_ONLY:
            return ['palak']
        elif roll < Config.PROB_NIYATI_ONLY + Config.PROB_PALAK_ONLY + Config.PROB_BOTH:
            res = ['niyati', 'palak']
            rng.shuffle(res)
            return res
            
        return []

    async def wait_for_turn(self, bot_name: str, chat_id: int, planned: List[str]):
        """
        If bot is 2nd in plan, wait until 1st bot adds response to transcript.
        """
        if not planned or planned[0] == bot_name:
            return  # We are first or only
            
        if len(planned) > 1 and planned[1] == bot_name:
            logger.info(f"[{bot_name}] Waiting for {planned[0]} to respond first...")
            start_wait = datetime.now(timezone.utc)
            timeout = Config.SECOND_BOT_TIMEOUT
            
            while (datetime.now(timezone.utc) - start_wait).total_seconds() < timeout:
                await asyncio.sleep(0.5)
                room = await self.get_room(chat_id)
                async with room.lock:
                    if room.last_responder == planned[0]:
                        logger.info(f"[{bot_name}] {planned[0]} responded. My turn!")
                        break
            else:
                logger.warning(f"[{bot_name}] Wait for {planned[0]} timed out! Responding anyway.")
                
            await asyncio.sleep(Config.SECOND_BOT_DELAY)

# Singleton
group_manager = GroupRoomManager()
