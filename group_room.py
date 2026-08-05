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
from dataclasses import dataclass, field
from config import Config, logger


@dataclass
class TriggerState:
    planned_responders: List[str] = field(default_factory=list)
    responded_bots: Set[str] = field(default_factory=set)
    inflight_bots: Set[str] = field(default_factory=set)
    last_responder: Optional[str] = None
    total_bot_replies: int = 0
    consecutive_bot_replies: int = 0
    closed: bool = False
    completion_event: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
        
        # Per-trigger state: {trigger_message_id: TriggerState}
        self.triggers: Dict[int, TriggerState] = {}
        self.bot_message_to_trigger: Dict[int, int] = {}
        
        # Deduplication state
        self.processed_by_bot: Set[Tuple[str, int]] = set()  # (bot_name, message_id)
        self.transcript_keys: Set[int] = set()   # message_id
        
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

    def get_trigger(self, trigger_message_id: int) -> Optional[TriggerState]:
        return self.triggers.get(trigger_message_id)

    def _cleanup_old_state(self):
        """Keep only recent state to prevent memory leak."""
        if len(self.triggers) > 200:
            keys = sorted(self.triggers.keys())
            for k in keys[:100]:
                del self.triggers[k]
        if len(self.bot_message_to_trigger) > 200:
            keys = sorted(self.bot_message_to_trigger.keys())
            for k in keys[:100]:
                del self.bot_message_to_trigger[k]
        if len(self.processed_by_bot) > 1000:
            self.processed_by_bot = set(list(self.processed_by_bot)[-500:])
        if len(self.transcript_keys) > 1000:
            self.transcript_keys = set(list(self.transcript_keys)[-500:])


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
                                    reply_to_bot_name: str = None) -> Tuple[bool, List[str], int]:
        """
        Process an incoming human message.
        
        Returns (should_proceed, planned_responders, trigger_message_id).
        """
        room = await self.get_room(chat_id)
        
        async with room.lock:
            # 1. Handler Processing Dedupe
            bot_msg_key = (bot_name, message_id)
            if bot_msg_key in room.processed_by_bot:
                trigger = room.get_trigger(message_id)
                plan = trigger.planned_responders if trigger else []
                return False, plan, message_id
            room.processed_by_bot.add(bot_msg_key)
            
            # 2. Check if trigger already exists for this message_id (set by the other bot)
            existing_trigger = room.get_trigger(message_id)
            if existing_trigger is not None:
                if existing_trigger.closed:
                    return False, [], message_id
                # Plan already computed by the other bot
                return True, existing_trigger.planned_responders, message_id

            # 3. First bot to see this message: create trigger and update session
            plan = self._decide_responders(room, message_id, sender_id, text, reply_to_bot_name)
            new_trigger = TriggerState(planned_responders=plan)
            room.triggers[message_id] = new_trigger
            
            logger.info(f"[Coordinator] Message {message_id} -> {plan}")
            
            # 4. Transcript Dedupe
            transcript_key = message_id
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
            
            # 5. Update Session State
            now = datetime.now(timezone.utc)
            room.active_human_user_id = sender_id
            room.last_human_message_at = now
            room.active_until = now + timedelta(seconds=75)
            room.conversation_depth += 1
            
            # 6. Cleanup old data
            room._cleanup_old_state()
                
            return True, plan, message_id

    async def reserve_bot(self, bot_name: str, chat_id: int, trigger_message_id: int) -> bool:
        """Atomically reserve a bot before starting an AI path."""
        room = await self.get_room(chat_id)
        async with room.lock:
            trigger = room.get_trigger(trigger_message_id)
            if not trigger:
                return False
            if bot_name in trigger.responded_bots or bot_name in trigger.inflight_bots:
                return False
            trigger.inflight_bots.add(bot_name)
            return True

    async def release_bot(self, bot_name: str, chat_id: int, trigger_message_id: int):
        """Release the reservation on failure."""
        room = await self.get_room(chat_id)
        async with room.lock:
            trigger = room.get_trigger(trigger_message_id)
            if trigger and bot_name in trigger.inflight_bots:
                trigger.inflight_bots.remove(bot_name)

    async def add_bot_message(self, bot_name: str, bot_id: int, chat_id: int, message_id: int, 
                              bot_display_name: str, text: str, trigger_message_id: int):
        """
        Add a bot's response to the transcript and count it.
        Bots DO NOT open or refresh human sessions.
        """
        room = await self.get_room(chat_id)
        
        async with room.lock:
            if not room.has_active_human_session():
                return
                
            transcript_key = message_id
            if transcript_key not in room.transcript_keys:
                room.transcript_keys.add(transcript_key)
                room.transcript.append({
                    'message_id': message_id,
                    'sender_name': bot_display_name,
                    'sender_id': bot_id,
                    'content': text,
                    'is_bot': True,
                    'bot_name': bot_name,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            
            # Update trigger state
            trigger = room.get_trigger(trigger_message_id)
            if trigger:
                room.bot_message_to_trigger[message_id] = trigger_message_id
                if bot_name in trigger.inflight_bots:
                    trigger.inflight_bots.remove(bot_name)
                    trigger.total_bot_replies += 1
                    trigger.last_responder = bot_name
                    trigger.responded_bots.add(bot_name)
                elif bot_name not in trigger.responded_bots:
                    trigger.total_bot_replies += 1
                    trigger.last_responder = bot_name
                    trigger.responded_bots.add(bot_name)
                    
                if len(trigger.responded_bots) >= len(trigger.planned_responders):
                    trigger.closed = True

    async def process_partner_message(self, bot_name: str, chat_id: int, message_id: int, 
                                      partner_id: int, partner_name: str, text: str,
                                      trigger_message_id: Optional[int]) -> Tuple[bool, List[str]]:
        """
        Process a message sent by the partner bot.
        """
        room = await self.get_room(chat_id)
        
        async with room.lock:
            # 1. Deduplicate
            bot_msg_key = (bot_name, message_id)
            if bot_msg_key in room.processed_by_bot:
                return False, []
            room.processed_by_bot.add(bot_msg_key)
            
            # 2. Add to transcript with real partner_id
            transcript_key = message_id
            if transcript_key not in room.transcript_keys:
                room.transcript_keys.add(transcript_key)
                partner_bot_name = self.get_partner_name(bot_name)
                room.transcript.append({
                    'message_id': message_id,
                    'sender_name': partner_name,
                    'sender_id': partner_id,
                    'content': text,
                    'is_bot': True,
                    'bot_name': partner_bot_name,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            
            if trigger_message_id is None:
                return False, []
                
            # Lookup original human trigger if it's a bot-to-bot reply
            if trigger_message_id in room.bot_message_to_trigger:
                trigger_message_id = room.bot_message_to_trigger[trigger_message_id]

            trigger = room.get_trigger(trigger_message_id)
            if not trigger:
                return False, []
                
            if trigger.closed:
                logger.debug(f"[{bot_name}] Trigger {trigger_message_id} is closed. Ignoring partner reaction.")
                return False, []
                
            # We add to transcript, but we NEVER authorize AI generation for a partner message
            return False, []

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

    async def wait_for_turn(self, bot_name: str, chat_id: int, planned: List[str], trigger_message_id: int):
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
                    trigger = room.get_trigger(trigger_message_id)
                    if trigger and trigger.last_responder == planned[0]:
                        logger.info(f"[{bot_name}] {planned[0]} responded. My turn!")
                        break
            else:
                logger.warning(f"[{bot_name}] Wait for {planned[0]} timed out! Responding anyway.")
                
            await asyncio.sleep(Config.SECOND_BOT_DELAY)

# Singleton
group_manager = GroupRoomManager()

