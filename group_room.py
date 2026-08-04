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
        self.trigger_message_id: Optional[int] = None
        self.last_human_message_at: Optional[datetime] = None
        self.active_until: Optional[datetime] = None
        self.conversation_depth: int = 0
        self.last_responder: Optional[str] = None
        self.planned_responders: List[str] = []
        
        # Bot-to-bot tracking
        self.total_bot_replies: int = 0
        self.consecutive_bot_replies: int = 0
        
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
        if bot_name.lower() == 'niyati':
            self.niyati_present = is_present
        elif bot_name.lower() == 'palak':
            self.palak_present = is_present

    def is_partner_present(self, my_bot_name: str) -> Optional[bool]:
        if my_bot_name.lower() == 'niyati':
            return self.palak_present
        elif my_bot_name.lower() == 'palak':
            return self.niyati_present
        return None

class GroupRoomManager:
    def __init__(self):
        self._rooms: Dict[int, GroupRoomState] = {}
        self._global_lock = asyncio.Lock()
        self._bot_ids: Dict[str, int] = {}
        
    def register_bot(self, bot_name: str, bot_id: int):
        self._bot_ids[bot_name.lower()] = bot_id
        
    def get_bot_id(self, bot_name: str) -> Optional[int]:
        return self._bot_ids.get(bot_name.lower())
        
    async def update_presence(self, chat_id: int, bot_name: str, is_present: bool):
        room = await self.get_room(chat_id)
        room.update_presence(bot_name, is_present)

    async def get_room(self, chat_id: int) -> GroupRoomState:
        async with self._global_lock:
            if chat_id not in self._rooms:
                self._rooms[chat_id] = GroupRoomState(chat_id)
            return self._rooms[chat_id]

    async def process_human_message(self, bot_name: str, chat_id: int, message_id: int, 
                                    sender_id: int, sender_name: str, text: str) -> bool:
        """
        Process an incoming human message.
        Returns True if this bot should proceed with handling.
        Returns False if this bot has already processed this message.
        """
        room = await self.get_room(chat_id)
        
        async with room.lock:
            # First bot to process this human message calculates the plan
            if not room.planned_responders and (bot_name, message_id) not in room.processed_by_bot:
                # 2. Determine who should respond
                room.planned_responders = self._decide_responders(room, message_id, sender_id, text)
                
                logger.info(f"🎯 [Coordinator] Message {message_id} -> {room.planned_responders}")
                
            # 1. Handler Processing Dedupe
            bot_msg_key = (bot_name, message_id)
            if bot_msg_key in room.processed_by_bot:
                logger.debug(f"👥 [{bot_name}] Deduplicated human message {message_id}")
                return False, room.planned_responders
            room.processed_by_bot.add(bot_msg_key)
            
            # 2. Transcript Dedupe
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
            
            # Update Session State (Open/Refresh session)
            now = datetime.now(timezone.utc)
            room.active_human_user_id = sender_id
            room.trigger_message_id = message_id
            room.last_human_message_at = now
            room.active_until = now + timedelta(seconds=75) # Configurable session expiry
            room.conversation_depth += 1
            
            # 4. Reset Bot-to-Bot depth tracking on human message
            room.total_bot_replies = 0
            room.consecutive_bot_replies = 0
            
            # Clean up old dedup sets to prevent memory leak (keep recent 1000)
            if len(room.processed_by_bot) > 1000:
                room.processed_by_bot = set(list(room.processed_by_bot)[-500:])
            if len(room.transcript_keys) > 1000:
                room.transcript_keys = set(list(room.transcript_keys)[-500:])
                
            return True, room.planned_responders

    async def add_bot_message(self, bot_name: str, chat_id: int, message_id: int, 
                              bot_display_name: str, text: str):
        """
        Add a bot's response to the transcript.
        Bots DO NOT open new sessions.
        """
        room = await self.get_room(chat_id)
        
        async with room.lock:
            # Bots only add to transcript if there's an active session
            if not room.has_active_human_session():
                logger.debug(f"👥 [{bot_name}] Ignored bot message - no active human session")
                return
                
            transcript_key = (message_id, 0) # 0 for bot self-messages, or just use 0
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
            
            # Reset conversation depth or update last responder
            room.last_responder = bot_name

    async def process_partner_message(self, bot_name: str, chat_id: int, message_id: int, 
                                      partner_id: int, partner_name: str, text: str) -> Tuple[bool, List[str]]:
        """
        Process a message sent by the partner bot.
        Limits consecutive bot replies and max total bot replies per human session.
        """
        room = await self.get_room(chat_id)
        
        async with room.lock:
            # 1. Deduplicate
            bot_msg_key = (bot_name, message_id)
            if bot_msg_key in room.processed_by_bot:
                return False, []
            room.processed_by_bot.add(bot_msg_key)
            
            # 2. Constraints Check
            if not room.has_active_human_session():
                logger.debug(f"🛑 [{bot_name}] Ignored partner bot message - no active human session")
                return False, []
                
            if room.total_bot_replies >= Config.MAX_BOT_REPLIES_PER_HUMAN_MESSAGE:
                logger.debug(f"🛑 [{bot_name}] Ignored partner bot message - max total bot replies reached")
                return False, []
                
            if room.consecutive_bot_replies >= Config.MAX_CONSECUTIVE_BOT_TO_BOT_REPLIES:
                logger.debug(f"🛑 [{bot_name}] Ignored partner bot message - max consecutive bot replies reached")
                return False, []
                
            # 3. Determine if this bot should respond to the partner
            planned = self._decide_responders(room, message_id, partner_id, text)
            if bot_name not in planned:
                return False, planned
                
            # 4. We are responding to a bot, increment counters
            room.total_bot_replies += 1
            room.consecutive_bot_replies += 1
            
            return True, planned

    async def get_transcript(self, chat_id: int, limit: int = 15) -> List[Dict]:
        """Get the shared transcript for this room."""
        room = await self.get_room(chat_id)
        async with room.lock:
            return list(room.transcript)[-limit:]

    def _decide_responders(self, room: GroupRoomState, message_id: int, sender_id: int, text: str) -> List[str]:
        """
        Deterministic seeded random decision of who responds.
        Seed: chat_id:message_id:sender_id
        """
        # 🔴 Phase 7: Single bot presence override
        if room.niyati_present is True and room.palak_present is False:
            return ['niyati']
        if room.palak_present is True and room.niyati_present is False:
            return ['palak']
            
        seed_str = f"{room.chat_id}:{message_id}:{sender_id}"
        seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
        rng = random.Random(seed_int)
        
        text_lower = text.lower()
        
        # Priority 1: "dono" or mentioning both explicitly
        if "dono" in text_lower or ("niyati" in text_lower and "palak" in text_lower):
            # Shuffle order
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
            logger.info(f"⏳ [{bot_name}] Waiting for {planned[0]} to respond first...")
            # We are second. Wait until transcript contains 1st bot's response, or timeout
            start_wait = datetime.now(timezone.utc)
            timeout = Config.SECOND_BOT_TIMEOUT
            
            while (datetime.now(timezone.utc) - start_wait).total_seconds() < timeout:
                await asyncio.sleep(0.5)
                # Check transcript
                room = await self.get_room(chat_id)
                async with room.lock:
                    if room.last_responder == planned[0]:
                        # 1st bot responded!
                        logger.info(f"✅ [{bot_name}] {planned[0]} responded. My turn!")
                        break
            else:
                logger.warning(f"⚠️ [{bot_name}] Wait for {planned[0]} timed out! Responding anyway.")
                
            # Add the configurable delay before second bot speaks
            await asyncio.sleep(Config.SECOND_BOT_DELAY)

# Singleton
group_manager = GroupRoomManager()
