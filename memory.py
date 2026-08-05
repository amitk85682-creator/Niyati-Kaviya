"""
╔══════════════════════════════════════════════════════╗
║           MEMORY MANAGER                              ║
║   Per-User + Per-Group Memory with Context Builder    ║
║   🔴 FIXES: Shared group memory across bots           ║
║   Both bots see ALL messages (users + each other)     ║
╚══════════════════════════════════════════════════════╝
"""

from typing import List, Dict, Optional
from collections import defaultdict, deque
from datetime import datetime, timezone

from config import Config, logger
from database import db


from group_room import group_manager


class MemoryManager:
    """
    Per-user, per-bot memory manager.
    
    Group memory is now SHARED across bots via _shared_group_threads.
    Private memory remains isolated per-bot.
    """

    def __init__(self, bot_name: str):
        self.bot_name = bot_name
        
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

    # Note: adding group/bot messages is now handled directly by group_manager in messages.py
    # But for backward compatibility we can keep these methods as no-ops or redirect them.
    # We will remove them here to enforce the new GroupRoomManager logic.

    async def get_group_context(self, chat_id: int, current_user_id: int,
                          current_user_name: str) -> List[Dict]:
        """
        Build group context for AI from SHARED memory.
        
        Returns recent group messages WITH identity,
        so the AI knows WHO said WHAT — including the other bot.
        """
        shared = await group_manager.get_transcript(chat_id, limit=15)
        
        context = []
        for msg in shared:
            sender = msg.get('sender_name', 'Someone')
            content = msg.get('content', '')
            is_bot = msg.get('is_bot', False)
            msg_bot_name = msg.get('bot_name', None)
            
            # If this message is from THIS bot, mark as assistant
            if is_bot and msg_bot_name == self.bot_name:
                context.append({
                    'role': 'assistant',
                    'content': content
                })
            # If from the OTHER bot, show as a named participant
            elif is_bot:
                context.append({
                    'role': 'user',
                    'content': f"[{sender}]: {content}"
                })
            # User message
            else:
                context.append({
                    'role': 'user',
                    'content': f"[{sender}]: {content}"
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
        
        Group context is now from SHARED memory — includes
        messages from users AND the other bot.
        """
        if is_group:
            context = await self.get_group_context(chat_id, user_id, user_name)
            
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
