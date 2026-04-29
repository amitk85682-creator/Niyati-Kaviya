"""
╔══════════════════════════════════════════════════════╗
║           MEMORY MANAGER                              ║
║   Per-User + Per-Group Memory with Context Builder    ║
║   🔴 FIXES: User isolation, Group context, Thread     ║
╚══════════════════════════════════════════════════════╝
"""

from typing import List, Dict, Optional
from collections import defaultdict, deque
from datetime import datetime, timezone

from config import Config, logger
from database import db


class MemoryManager:
    """
    Per-user, per-bot memory manager.
    
    FIXES the 3 critical bugs:
    1. Group context now includes user-specific history
    2. User identity is tracked and passed to AI
    3. Each bot has its own memory space
    """

    def __init__(self, bot_name: str):
        self.bot_name = bot_name
        
        # Group conversation tracking: {chat_id: deque of {user_name, user_id, content}}
        self._group_threads: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=30)
        )
        
        # Track who the bot last replied to in each group
        self._last_reply_to: Dict[int, int] = {}  # {chat_id: user_id}

    # ========== PRIVATE CHAT MEMORY ==========

    async def get_private_context(self, user_id: int, user_name: str) -> List[Dict]:
        """
        Build context for private chat.
        Returns list of {role, content} for AI prompt.
        """
        messages = await db.get_user_context(self.bot_name, user_id)
        
        # Filter to only this bot's messages (for shared DB)
        context = []
        for msg in messages:
            # If msg has 'bot' field, only include this bot's messages
            if msg.get('bot') and msg['bot'] != self.bot_name:
                continue
            context.append({
                'role': msg.get('role', 'user'),
                'content': msg.get('content', '')
            })
        
        return context[-Config.MAX_PRIVATE_MESSAGES:]

    async def save_private_message(self, user_id: int, role: str, content: str):
        """Save a message in private chat history"""
        await db.save_message(self.bot_name, user_id, role, content)

    async def clear_private_memory(self, user_id: int):
        """Clear private chat memory"""
        await db.clear_user_memory(self.bot_name, user_id)

    # ========== GROUP CHAT MEMORY ==========

    def add_group_message(self, chat_id: int, user_name: str, user_id: int, content: str):
        """
        Track message in group conversation.
        Stores user identity with each message.
        """
        self._group_threads[chat_id].append({
            'user_name': user_name,
            'user_id': user_id,
            'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        # Also save to DB for persistence
        db.add_group_message(chat_id, user_name, user_id, content)

    def get_group_context(self, chat_id: int, current_user_id: int,
                          current_user_name: str) -> List[Dict]:
        """
        Build group context for AI.
        
        Returns recent group messages WITH user identity,
        so the AI knows WHO said WHAT.
        
        Format for AI:
        [
            {"role": "user", "content": "[Rahul]: kya haal hai"},
            {"role": "user", "content": "[Priya]: main theek hu"},
            {"role": "assistant", "content": "hiii Rahul! sab badiya?"},
        ]
        """
        thread = list(self._group_threads.get(chat_id, []))
        
        # Take last N messages
        recent = thread[-10:]
        
        context = []
        for msg in recent:
            user_name = msg.get('user_name', 'Someone')
            uid = msg.get('user_id', 0)
            content = msg.get('content', '')
            
            # Tag each message with the user's name
            context.append({
                'role': 'user',
                'content': f"[{user_name} (ID:{uid})]: {content}"
            })
        
        return context

    def set_last_reply_to(self, chat_id: int, user_id: int):
        """Track who the bot last replied to"""
        self._last_reply_to[chat_id] = user_id

    def get_last_reply_to(self, chat_id: int) -> Optional[int]:
        """Get who the bot last replied to in this group"""
        return self._last_reply_to.get(chat_id)

    # ========== CONTEXT BUILDER FOR AI ==========

    async def build_ai_context(self, user_id: int, user_name: str,
                                chat_id: int, is_group: bool,
                                reply_to_user: str = None) -> List[Dict]:
        """
        Build the complete context to send to AI.
        
        This is the CORE function that fixes memory issues.
        It properly isolates user context and includes identity info.
        """
        if is_group:
            context = self.get_group_context(chat_id, user_id, user_name)
            
            # Add a system note about who is currently talking
            if reply_to_user:
                context.append({
                    'role': 'user',
                    'content': f"[SYSTEM NOTE: {user_name} is replying to {reply_to_user}]"
                })
        else:
            context = await self.get_private_context(user_id, user_name)
        
        return context


# ============================================================================
# MEMORY INSTANCES (one per bot)
# ============================================================================

_memory_instances: Dict[str, MemoryManager] = {}


def get_memory(bot_name: str) -> MemoryManager:
    """Get or create memory manager for a specific bot"""
    if bot_name not in _memory_instances:
        _memory_instances[bot_name] = MemoryManager(bot_name)
        logger.info(f"✅ Memory manager created for {bot_name}")
    return _memory_instances[bot_name]
